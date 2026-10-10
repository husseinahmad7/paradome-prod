from functools import wraps
import json
from pathlib import Path
import uuid

from django.conf import settings
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotFound, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET, require_POST, require_safe

from Domes.ratelimits import rate_limit
from . import services, triage
from .forms import DeliveryForm, SearchForm, SubmissionForm
from .models import LabRun
from .permissions import permission_explorer


DEFAULT_TEXT = "The export button returns an error after I select a date range."
SOURCE_BASE = "https://github.com/husseinahmad7/paradome-prod/blob/main"
OUTCOME_MESSAGES = {
    "reset": "A fresh private run is ready. Your previous run was removed.",
    "submitted": "Submission and event committed together. Choose a delivery scenario below.",
    "replayed": "The original submission was returned. No extra event was created.",
    "acknowledged": "Delivery acknowledged. The destination contains one inbox effect for this event.",
    "already_acknowledged": "This event is already acknowledged; no new attempt or inbox effect was created.",
    "fail_before_delivery": "Failure occurred before delivery. There is no new destination effect; try again when ready.",
    "lost_ack": "The inbox effect committed, but the acknowledgement was lost. Retry successfully to see duplicate prevention.",
    "stale": "The attempt's lease ended or another attempt replaced it. Its late result did not overwrite current state.",
}


def lab_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.ENGINEERING_LAB_ENABLED:
            response = HttpResponseNotFound("Not found")
        else:
            try:
                response = view(request, *args, **kwargs)
            except Http404:
                response = JsonResponse({"error": "Run unavailable. Start a new run in this browser."}, status=404) if _wants_json(request) else render(request, "engineering/error.html", {
                    "reason": "Run unavailable",
                    "message": "This run has expired or belongs to another browser session. Start a new run to continue. Signing out also ends access to existing runs.",
                }, status=404)
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        patch_vary_headers(response, ["HX-Request", "Cookie"])
        return response
    return wrapped


def _wants_json(request):
    return request.content_type == "application/json" or "application/json" in request.headers.get("Accept", "")


def lab_rate_limit(scope, *, limit, window_seconds):
    """Keep the shared IP limiter, but render its rejection in the lab shell."""
    def decorator(view):
        limited_view = rate_limit(
            scope, limit=limit, window_seconds=window_seconds, identity_modes=("ip",),
        )(view)

        @wraps(view)
        def wrapped(request, *args, **kwargs):
            response = limited_view(request, *args, **kwargs)
            if response.status_code != 429 or not response.has_header("Retry-After"):
                return response
            retry_after = response["Retry-After"]
            message = (
                f"Requests from this network are temporarily limited. Wait {retry_after} seconds, "
                "then try again. Your saved lab records have not been changed."
            )
            try:
                run_id = kwargs.get("run_id") or (args[0] if args else None)
                if run_id is not None:
                    # Never render any run state before rechecking ownership.
                    run = services.owned_run(request, run_id)
                    bound_forms = {}
                    if scope == "engineering-submit":
                        bound_forms["submission_form"] = SubmissionForm(request.POST)
                    elif scope == "engineering-deliver":
                        bound_forms["delivery_form"] = DeliveryForm(request.POST)
                    response = _state(request, run, status=429, error=message, **bound_forms)
                else:
                    response = render(request, "engineering/error.html", {
                        "reason": "Slow down for a moment", "message": message,
                        "is_throttled": True, "retry_after": retry_after,
                    }, status=429)
            except DatabaseError:
                # The shared limiter intentionally fails closed on DB failures.
                # Do not turn its safe429 into a500 by trying to load lab state.
                response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
            response["Retry-After"] = retry_after
            return response
        return wrapped
    return decorator


def _state_context(run, *, submission_form=None, delivery_form=None, feedback="", error=""):
    submissions = list(run.submissions.select_related("event", "event__receipt"))
    events = [submission.event for submission in submissions]
    receipts = [event.receipt for event in events if hasattr(event, "receipt")]
    context = {
        "run": run,
        "submissions": submissions,
        "events": events,
        "receipts": receipts,
        "traces": list(run.traces.select_related("event")),
        "submission_form": submission_form if submission_form is not None else SubmissionForm(initial={"text": DEFAULT_TEXT, "idempotency_key": uuid.uuid4()}),
        "delivery_form": delivery_form if delivery_form is not None else DeliveryForm(initial={"event_id": events[-1].id if events else None, "scenario": "lost_ack"}),
        "feedback": feedback,
        "error": error,
        "model_card": triage.model_card(),
        "source_base": "https://github.com/husseinahmad7/paradome-prod/blob/" + settings.ENGINEERING_SOURCE_REVISION,
        "can_submit": len(submissions) < services.MAX_SUBMISSIONS,
        "elapsed_seconds": max(0, (timezone.now() - run.created_at).total_seconds()),
        "session_expiry_note": "Runs last at most 24 hours. Signing out or your browser session expiring ends access sooner; the lab does not extend your login.",
    }
    context["control_room_enabled"] = settings.ENGINEERING_CONTROL_ROOM_ENABLED
    if settings.ENGINEERING_CONTROL_ROOM_ENABLED:
        from . import search as retrieval
        try:
            worker_version = json.loads(retrieval.ROOT.joinpath("assets-lock-v1.json").read_bytes())["assets"]["worker.mjs"]["sha256"]
        except (OSError, ValueError, KeyError):
            worker_version = "unavailable"
        context.update({"search_form": SearchForm(initial={"text": "A double click creates two tickets. How do I make repeated requests return the first one?"}),
                        "worker_version": worker_version,
                        "search_contract": retrieval.embedding_contract(), "search_health": retrieval.artifact_health(),
                        "evaluation": retrieval.evaluation_report(), "metrics": retrieval.metrics(run)})
    return context


def _state(request, run, *, status=200, **kwargs):
    template = "engineering/_state.html" if request.headers.get("HX-Request") == "true" else "engineering/run.html"
    response = render(request, template, _state_context(run, **kwargs), status=status)
    response["X-Lab-State"] = "1"
    return response


def _redirect(request, run, outcome=None):
    location = reverse("engineering:run_detail", args=[run.id])
    if outcome:
        location += "?outcome=" + outcome
    response = HttpResponse(status=303)
    response["Location"] = location
    if request.headers.get("HX-Request") == "true":
        response.status_code = 200
        response["HX-Redirect"] = location
    return response


@lab_page
@require_GET
def index(request):
    return render(request, "engineering/index.html", {"model_card": triage.model_card(), "source_base": SOURCE_BASE, "control_room_enabled": settings.ENGINEERING_CONTROL_ROOM_ENABLED})


@lab_page
@require_POST
@lab_rate_limit("engineering-start", limit=12, window_seconds=3600)
def create_run(request):
    try:
        run = services.create_run(request)
    except services.LabCapacity as exc:
        return render(request, "engineering/error.html", {
            "reason": "Run limit reached",
            "message": str(exc),
            "existing_runs": LabRun.objects.filter(owner_hash=services.owner_hash(request), expires_at__gt=timezone.now()),
        }, status=429)
    return _redirect(request, run)


@lab_page
@require_GET
def run_detail(request, run_id):
    run = services.owned_run(request, run_id)
    if settings.ENGINEERING_CONTROL_ROOM_ENABLED and request.GET.get("discussion"):
        from . import search as retrieval
        document = next((doc for doc in retrieval.corpus()[0]["documents"] if doc["id"] == request.GET["discussion"]), None)
        if document:
            return _state(request, run, submission_form=SubmissionForm(initial={"text": document["text"], "idempotency_key": uuid.uuid4()}), feedback="Discussion selected. Submit it, then try the lost acknowledgement scenario.")
    return _state(request, run, feedback=OUTCOME_MESSAGES.get(request.GET.get("outcome"), ""))


@lab_page
@require_POST
@lab_rate_limit("engineering-submit", limit=40, window_seconds=300)
def submit(request, run_id):
    run = services.owned_run(request, run_id)
    form = SubmissionForm(request.POST)
    if not form.is_valid():
        return _state(request, run, submission_form=form, status=400, error="Check the submission fields below.")
    try:
        prediction = triage.classify(form.cleaned_data["text"])
        submission, created = services.submit(run, form.cleaned_data["idempotency_key"], form.cleaned_data["text"], prediction)
    except services.LabConflict as exc:
        return _state(request, run, submission_form=form, status=409, error=str(exc))
    except services.LabCapacity as exc:
        return _state(request, run, submission_form=form, status=429, error=str(exc))
    outcome = "submitted" if created else "replayed"
    if request.headers.get("HX-Request") == "true":
        return _state(request, run, feedback=OUTCOME_MESSAGES[outcome], status=201 if created else 200)
    return _redirect(request, run, outcome)


@transaction.non_atomic_requests
@lab_page
@require_POST
@lab_rate_limit("engineering-deliver", limit=40, window_seconds=300)
def delivery(request, run_id):
    run = services.owned_run(request, run_id)
    form = DeliveryForm(request.POST)
    if not form.is_valid():
        return _state(request, run, delivery_form=form, status=400, error="Choose one of the provided delivery scenarios.")
    try:
        outcome = services.attempt_delivery(run, form.cleaned_data["event_id"], form.cleaned_data["scenario"])
    except services.LabConflict as exc:
        return _state(request, run, delivery_form=form, status=409, error=str(exc))
    except services.LabCapacity as exc:
        return _state(request, run, delivery_form=form, status=429, error=str(exc))
    if request.headers.get("HX-Request") == "true":
        return _state(request, run, feedback=OUTCOME_MESSAGES[outcome])
    return _redirect(request, run, outcome)


@lab_page
@require_POST
@lab_rate_limit("engineering-reset", limit=12, window_seconds=3600)
def reset(request, run_id):
    run = services.owned_run(request, run_id)
    replacement = services.reset_run(request, run)
    return _redirect(request, replacement, "reset")


@lab_page
@require_GET
def permissions(request):
    context = permission_explorer(request.GET)
    context["source_base"] = SOURCE_BASE
    return render(request, "engineering/permissions.html", context)


def control_room_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.ENGINEERING_CONTROL_ROOM_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def search_rate_limit(view):
    limited = rate_limit("engineering-search", limit=40, window_seconds=300, identity_modes=("ip",))(view)

    @wraps(view)
    def wrapped(request, run_id):
        # Ownership precedes throttling so no rejection reveals another run.
        services.owned_run(request, run_id)
        response = limited(request, run_id)
        if response.status_code == 429 and _wants_json(request):
            retry = response.get("Retry-After", "300")
            response = JsonResponse({"error": "Search requests are temporarily limited. Wait and retry.", "retry_after": retry}, status=429)
            response["Retry-After"] = retry
        return response
    return wrapped


@lab_page
@control_room_page
@require_POST
@search_rate_limit
def search(request, run_id):
    from . import search as retrieval
    run = services.owned_run(request, run_id)
    embedding, browser, fallback, experimental = None, {}, "javascript_unavailable", False
    if request.content_type == "application/json":
        try:
            if len(request.body) > 12_288:
                raise ValueError
            payload = json.loads(request.body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise ValueError
            embedding = payload.get("embedding")
            browser = payload.get("browser", {})
            if not isinstance(browser, dict):
                raise ValueError
            fallback = payload.get("fallback", "model_loading")
            experimental = payload.get("experimental", False)
            if type(experimental) is not bool:
                raise ValueError
            if not isinstance(fallback, str):
                raise ValueError
            form = SearchForm({"text": payload["text"]})
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Use a JSON object with 3–240 characters of text and an optional versioned embedding (maximum 12 KB)."}, status=400)
    else:
        form = SearchForm(request.POST)
    if not form.is_valid():
        if _wants_json(request):
            return JsonResponse({"error": "Use 3–240 characters of plain English text."}, status=400)
        context = _state_context(run)
        context["search_form"] = form
        context["error"] = "Check the search field. Use 3–240 characters."
        return render(request, "engineering/run.html", context, status=400)
    result = retrieval.retrieve(form.cleaned_data["text"], embedding, fallback=fallback, experimental=experimental)
    retrieval.record_observation(run, result, browser)
    if _wants_json(request):
        return JsonResponse(result)
    context = _state_context(run)
    context.update({"search_form": form, "search_result": result})
    return render(request, "engineering/run.html", context)


@lab_page
@control_room_page
@require_GET
def metrics(request, run_id):
    from . import search as retrieval
    return JsonResponse(retrieval.metrics(services.owned_run(request, run_id)))


@lab_page
@control_room_page
@require_GET
def evaluation(request):
    from . import search as retrieval
    report = retrieval.evaluation_report()
    if _wants_json(request):
        return JsonResponse(report)
    return render(request, "engineering/evaluation.html", {"evaluation": report, "source_base": SOURCE_BASE})


@lab_page
@control_room_page
@require_GET
def embedding_goldens(request):
    from . import search as retrieval
    try:
        golden = json.loads(retrieval.ARTIFACT_ROOT.joinpath("search-golden-v1.json").read_bytes())
        index = json.loads(retrieval.ARTIFACT_ROOT.joinpath("search-index-v1.json").read_bytes())
        golden["reference_index"] = {"document_ids": index["document_ids"], "vectors": index["vectors"]}
        return JsonResponse(golden)
    except (OSError, ValueError):
        return JsonResponse({"error": "Golden artifact unavailable"}, status=503)


@require_safe
def search_asset(request, asset):
    """Allowlisted immutable public artifacts, including a narrowly scoped CSP.

    Serving original paths avoids hashed collectstatic rewriting ONNX runtime
    relative imports. No user uploads or private storage can reach this route.
    """
    if not settings.ENGINEERING_LAB_ENABLED or not settings.ENGINEERING_CONTROL_ROOM_ENABLED:
        raise Http404
    from . import search as retrieval
    prefix = "minilm-q8-v1/"
    if not asset.startswith(prefix):
        raise Http404
    relative = asset[len(prefix):]
    try:
        lock = json.loads(retrieval.ROOT.joinpath("assets-lock-v1.json").read_bytes())
    except (OSError, ValueError):
        raise Http404
    if relative not in lock["assets"] and relative != "manifest.json":
        raise Http404
    root = Path(__file__).resolve().parent / "static/engineering/search-assets/minilm-q8-v1"
    path = root / relative
    if not path.is_file():
        raise Http404
    content_type = "text/javascript" if relative.endswith((".mjs", ".js")) else "application/wasm" if relative.endswith(".wasm") else "application/json" if relative.endswith(".json") else "application/octet-stream"
    digest = lock["assets"].get(relative, {}).get("sha256")
    etag = '"' + digest + '"' if digest else None
    if etag and etag in request.headers.get("If-None-Match", "").split(", "):
        response = HttpResponseNotModified()
    elif request.method == "HEAD":
        response = HttpResponse(content_type=content_type)
        response["Content-Length"] = path.stat().st_size
    else:
        response = FileResponse(path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    if digest:
        response["ETag"] = etag
    if relative == "worker.mjs":
        response["Content-Security-Policy"] = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; worker-src 'none'; object-src 'none'"
    return response
