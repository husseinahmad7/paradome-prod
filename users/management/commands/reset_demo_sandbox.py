from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from Chat.models import ChatChannel, ChatMessage
from Domes.access import DEMO_GROUP_NAME
from Domes.models import Category, Dome
from messages.models import Message
from notify.models import Notification
from posts.models import Comment, Follow, Like, Post, Stream
from users.models import Profile


class Command(BaseCommand):
    help = "Reset the isolated guest sandbox to its canonical text-only fixture."

    @transaction.atomic
    def handle(self, *args, **options):
        username = getattr(settings, "DEMO_USERNAME", "")
        if not username:
            raise CommandError("DEMO_USERNAME must be configured.")

        demo_group, _ = Group.objects.get_or_create(name=DEMO_GROUP_NAME)
        demo_user = User.objects.select_for_update().filter(username=username).first()
        if demo_user is None:
            demo_user = User(username=username)
        elif not demo_user.groups.filter(pk=demo_group.pk).exists():
            raise CommandError(
                "DEMO_USERNAME belongs to a non-demo account; refusing to replace it."
            )

        demo_user.email = ""
        demo_user.first_name = "Guest"
        demo_user.last_name = ""
        demo_user.is_active = True
        demo_user.is_staff = False
        demo_user.is_superuser = False
        demo_user.set_unusable_password()
        demo_user.save()
        demo_user.groups.set([demo_group])
        demo_user.user_permissions.clear()

        # Remove both copies of any legacy direct conversation and every
        # interaction that could connect this sandbox identity to real users.
        Message.objects.filter(
            Q(user=demo_user) | Q(sender=demo_user) | Q(recipient=demo_user)
        ).delete()
        Notification.objects.filter(
            Q(user=demo_user) | Q(sender=demo_user)
        ).delete()
        Like.objects.filter(user=demo_user).delete()
        Follow.objects.filter(
            Q(follower=demo_user) | Q(following=demo_user)
        ).delete()
        Stream.objects.filter(
            Q(user=demo_user) | Q(following=demo_user)
        ).delete()
        Comment.objects.filter(user=demo_user).delete()
        Post.objects.filter(user=demo_user).delete()
        demo_user.dome_members.clear()
        demo_user.dome_moderators.clear()
        Dome.objects.filter(user=demo_user).delete()

        profile, _ = Profile.objects.get_or_create(user=demo_user)
        profile.first_name = "Guest"
        profile.last_name = ""
        profile.bio = "A resettable, isolated ParaDome guest sandbox."
        profile.favorite.clear()
        Profile.objects.filter(pk=profile.pk).update(
            first_name=profile.first_name,
            last_name=profile.last_name,
            bio=profile.bio,
            picture="profile_pics/default.jpg",
        )

        dome = Dome.objects.create(
            user=demo_user,
            title=getattr(settings, "DEMO_DOME_TITLE", "ParaDome Demo")[:25],
            description="A private sandbox for trying posts, replies, reactions, and chat.",
            privacy=0,
            icon=None,
            banner=None,
        )
        category = Category.objects.create(title="Getting started", Dome=dome)
        channel = ChatChannel.objects.create(
            title="general",
            topic="Try safe realtime chat here.",
            category=category,
        )
        post = Post.objects.create(
            user=demo_user,
            dome=dome,
            question_text="Welcome to the ParaDome demo",
            content=(
                "<p>This sandbox resets every day. Try a text post, comment, "
                "reaction, or chat message—nothing here reaches real users.</p>"
            ),
        )
        Comment.objects.create(
            user=demo_user,
            post=post,
            comment="<p>This is a seeded demo comment.</p>",
        )
        ChatMessage.objects.create(
            user=demo_user,
            channel=channel,
            body="Welcome. This demo channel is isolated and resets daily.",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reset demo sandbox for {demo_user.username} (Dome {dome.pk})."
            )
        )
