from smtplib import SMTPException

from django.conf import settings
from django.core.mail import BadHeaderError, EmailMultiAlternatives
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .forms import ContactMe


def home(request):
    return render(request, 'HusseinAh/myPortfolio.html')


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="3/h", method="POST", block=True)
def mailme(request):
    sent = False

    if request.method == 'POST':
        form = ContactMe(request.POST)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['content']
            visitor_email = form.cleaned_data['email']

            # Return the normal success state for honeypot submissions without
            # revealing the spam control or sending an email.
            if form.cleaned_data['website']:
                sent = True
                form = ContactMe()
            else:
                html = render_to_string(
                    'HusseinAh/mail.html',
                    {'email': visitor_email, 'message': message},
                )
                email = EmailMultiAlternatives(
                    subject=f"Portfolio contact: {subject}",
                    body=f"From: {visitor_email}\n\n{message}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[settings.CONTACT_RECIPIENT],
                    reply_to=[visitor_email],
                )
                email.attach_alternative(html, "text/html")

                try:
                    email.send(fail_silently=False)
                except (BadHeaderError, SMTPException, OSError):
                    form.add_error(
                        None,
                        "Your message could not be sent right now. Please try again or use the email address on the portfolio.",
                    )
                else:
                    sent = True
                    form = ContactMe()
    else:
        form = ContactMe()

    return render(
        request,
        'HusseinAh/feedback.html',
        {'form': form, 'sent': sent},
    )
