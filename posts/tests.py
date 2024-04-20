from django.test import TestCase, Client
import django
from django.contrib.auth.models import User
from .models import Post, Comment, Tag, Follow, Stream, Like
from Domes.models import Dome

class ModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user1 = User.objects.create_user(username='testuser1', password='testpass1')
        user2 = User.objects.create_user(username='testuser2', password='testpass2')

        dome = Dome.objects.create(name='Test Dome')

        tag1 = Tag.objects.create(title='Test Tag 1')
        tag2 = Tag.objects.create(title='Test Tag 2')

        Post.objects.create(
            user=user1,
            question_text='Test Post 1',
            content='Test content 1',
            dome=dome,
            tags=[tag1, tag2]
        )
        Post.objects.create(
            user=user2,
            question_text='Test Post 2',
            content='Test content 2',
            dome=dome,
            tags=[tag1]
        )


        Comment.objects.create(
            post=Post.objects.get(question_text='Test Post 1'),
            user=user1,
            comment='Test comment 1'
        )
        Comment.objects.create(
            post=Post.objects.get(question_text='Test Post 1'),
            user=user2,
            comment='Test comment 2',
            reply_to=Comment.objects.get(comment='Test comment 1')
        )


        Follow.objects.create(follower=user1, following=user2)

        Stream.objects.create(
            following=user1,
            user=user2,
            post=Post.objects.get(question_text='Test Post 2'),
            date=django.utils.timezone.now()
        )

        Like.objects.create(user=user1, post=Post.objects.get(question_text='Test Post 1'))

    def test_post_model(self):
        post = Post.objects.get(question_text='Test Post 1')
        self.assertEqual(post.user.username, 'testuser1')
        self.assertEqual(post.question_text, 'Test Post 1')
        self.assertEqual(post.content, 'Test content 1')
        self.assertEqual(post.dome.name, 'Test Dome')
        self.assertEqual(post.tags.count(), 2)
        self.assertEqual(post.likes, 1)

    def test_comment_model(self):
        comment = Comment.objects.get(comment='Test comment 1')
        self.assertEqual(comment.post.question_text, 'Test Post 1')
        self.assertEqual(comment.user.username, 'testuser1')
        self.assertEqual(comment.comment, 'Test comment 1')
        self.assertIsNone(comment.reply_to)

        comment2 = Comment.objects.get(comment='Test comment 2')
        self.assertEqual(comment2.post.question_text, 'Test Post 1')
        self.assertEqual(comment2.user.username, 'testuser2')
        self.assertEqual(comment2.comment, 'Test comment 2')
        self.assertEqual(comment2.reply_to.comment, 'Test comment 1')

    def test_tag_model(self):
        tag1 = Tag.objects.get(title='Test Tag 1')
        self.assertEqual(tag1.title, 'Test Tag 1')
        self.assertEqual(tag1.slug, 'test-tag-1')
        self.assertEqual(tag1.posts.count(), 2)

    def test_follow_model(self):
        follow = Follow.objects.get(follower__username='testuser1')
        self.assertEqual(follow.follower.username, 'testuser1')
        self.assertEqual(follow.following.username, 'testuser2')

    def test_stream_model(self):
        stream = Stream.objects.get(following__username='testuser1')
        self.assertEqual(stream.following.username, 'testuser1')
        self.assertEqual(stream.user.username, 'testuser2')
        self.assertEqual(stream.post.question_text, 'Test Post 2')
        self.assertEqual(stream.date, stream.post.posted_date)

    def test_like_model(self):
        like = Like.objects.get(user__username='testuser1')
        self.assertEqual(like.user.username, 'testuser1')
        self.assertEqual(like.post.question_text, 'Test Post 1')