from contextlib import nullcontext

from django.core.management.base import BaseCommand
from django.db import transaction

from posts.models import Comment, Post
from posts.sanitizers import sanitize_rich_text


class Command(BaseCommand):
    help = "Report or sanitize all persisted Post and Comment rich text."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        counts = {"posts_scanned": 0, "posts_changed": 0, "comments_scanned": 0, "comments_changed": 0}
        transaction_context = transaction.atomic() if apply_changes else nullcontext()

        with transaction_context:
            posts = Post.objects.all()
            comments = Comment.objects.all()
            if apply_changes:
                posts = posts.select_for_update()
                comments = comments.select_for_update()

            for post in posts.iterator(chunk_size=500):
                counts["posts_scanned"] += 1
                clean = sanitize_rich_text(post.content)
                if clean != post.content:
                    counts["posts_changed"] += 1
                    if apply_changes:
                        Post.objects.filter(pk=post.pk).update(content=clean)

            for comment in comments.iterator(chunk_size=500):
                counts["comments_scanned"] += 1
                clean = sanitize_rich_text(comment.comment)
                if clean != comment.comment:
                    counts["comments_changed"] += 1
                    if apply_changes:
                        Comment.objects.filter(pk=comment.pk).update(comment=clean)

        mode = "applied" if apply_changes else "dry-run"
        self.stdout.write(
            f"{mode}: posts {counts['posts_changed']}/{counts['posts_scanned']} changed; "
            f"comments {counts['comments_changed']}/{counts['comments_scanned']} changed."
        )
