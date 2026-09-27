"""Fixed, identity-free examples for the engineering permission explorer."""

from Domes.access import DomePolicyFacts, evaluate_dome_policy


ROLES = (
    ("anonymous", "Anonymous visitor"),
    ("outsider", "Signed-in outsider"),
    ("member", "Member"),
    ("moderator", "Moderator"),
    ("owner", "Owner (real account)"),
    ("demo", "Demo account"),
)
RESOURCES = (
    ("public", "Public Dome", "A real-account Dome with public reading enabled."),
    ("private", "Private Dome", "A real-account Dome restricted to its participants."),
    (
        "demo",
        "Demo sandbox",
        "The hypothetical Demo account owns this sandbox. Real accounts remain outside it.",
    ),
    (
        "other-demo",
        "Another demo sandbox",
        "A different Demo account owns this sandbox; even the selected Demo account is outside it.",
    ),
)
ACTIONS = (
    ("access", "Read Dome content"),
    ("create_content", "Create Dome content"),
    ("participate_chat", "Participate in chat"),
    ("manage", "Moderate content"),
    ("administer", "Change roles and settings"),
)


def _hypothetical_facts(role, resource):
    """No object identifier, request user, session, or database is accepted."""

    demo_owned = resource in {"demo", "other-demo"}
    return DomePolicyFacts(
        authenticated=role != "anonymous",
        demo_user=role == "demo",
        demo_owned=demo_owned,
        public=resource == "public",
        owner=(role == "owner" and not demo_owned)
        or (role == "demo" and resource == "demo"),
        # Deliberately retain these on demo-owned resources: accidental
        # membership or moderator rows must not bypass sandbox isolation.
        member=role == "member",
        moderator=role == "moderator",
    )


def _explanation(action, facts, allowed):
    if facts.demo_user:
        if not facts.owner:
            return "Demo accounts can use only their own sandbox, even when another Dome is public."
        if action in {"manage", "administer"}:
            return "Demo ownership allows participation, but never moderation or changes to roles and settings."
        return "The Demo account may read, post and chat inside the sandbox it owns."
    if facts.demo_owned:
        return "Demo sandboxes exclude real accounts, including accidental members and moderators."
    if action == "access":
        if facts.public:
            return "Public reading is allowed without membership; it does not grant posting or chat access."
        if allowed:
            return "Private reading requires the owner, a member or a moderator."
        return "An anonymous visitor or outsider cannot read a private Dome."
    if action == "administer":
        return "Only a real-account owner may change membership roles or Dome settings."
    if action in {"manage", "create_content"}:
        return "Only real-account owners and moderators may create or moderate Dome content."
    return "Chat requires a signed-in owner, member or moderator, even in a public Dome."


def permission_explorer(querydict):
    """Return template context for an allowlisted hypothetical scenario.

    Unknown inputs fall back to a private Dome and an anonymous visitor. The
    submitted strings are never echoed or used as real resource identifiers.
    """

    roles = dict(ROLES)
    resources = {value: (label, description) for value, label, description in RESOURCES}
    selected_role = querydict.get("role", "anonymous")
    if selected_role not in roles:
        selected_role = "anonymous"
    selected_resource = querydict.get("resource", "private")
    if selected_resource not in resources:
        selected_resource = "private"
    facts = _hypothetical_facts(selected_role, selected_resource)
    decision = evaluate_dome_policy(facts)
    resource_label, resource_description = resources[selected_resource]
    return {
        "roles": [{"value": value, "label": label} for value, label in ROLES],
        "resources": [
            {"value": value, "label": label, "description": description}
            for value, label, description in RESOURCES
        ],
        "selected_role": selected_role,
        "selected_resource": selected_resource,
        "role_label": roles[selected_role],
        "resource_label": resource_label,
        "resource_description": resource_description,
        "decisions": [
            {
                "action": action,
                "label": label,
                "allowed": getattr(decision, action),
                "explanation": _explanation(action, facts, getattr(decision, action)),
            }
            for action, label in ACTIONS
        ],
        "simulation_notice": (
            "A fixed hypothetical policy evaluation. Your account, roles and real Domes "
            "are never changed or inspected."
        ),
    }
