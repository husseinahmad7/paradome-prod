from django.test import TestCase, Client
from django.urls import reverse
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

class TestPostsListView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post1 = Post.objects.create(user=self.user, question_text='Test Post 1', content='Test content 1')
        self.post2 = Post.objects.create(user=self.user, question_text='Test Post 2', content='Test content 2')

    def test_posts_list_view(self):
        response = self.client.get(reverse('posts:posts'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/posts.html')
        self.assertContains(response, self.post1.question_text)
        self.assertContains(response, self.post2.question_text)

class TestUserPostsListView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post1 = Post.objects.create(user=self.user, question_text='Test Post 1', content='Test content 1')
        self.post2 = Post.objects.create(user=self.user, question_text='Test Post 2', content='Test content 2')

    def test_user_posts_list_view(self):
        response = self.client.get(reverse('posts:user-posts', args=[self.user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/user_posts.html')
        self.assertContains(response, self.post1.question_text)
        self.assertContains(response, self.post2.question_text)

class TestPostView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')

    def test_post_view(self):
        response = self.client.get(reverse('posts:post-detail', args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/post.html')
        self.assertContains(response, self.post.question_text)
        self.assertContains(response, self.post.content)

class TestPostCreateView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)

    def test_post_create_view(self):
        response = self.client.post(reverse('posts:post-create'), {'question_text': 'Test Post', 'content': 'Test content'})
        self.assertEqual(response.status_code, 302)
        # self.assertEqual(Post.objects.count(), 1)

class TestPostUpdateView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')

    def test_post_update_view(self):
        response = self.client.post(reverse('posts:post-update', args=[self.post.pk]), {'question_text': 'Updated Test Post', 'content': 'Updated Test content'})
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.question_text, 'Updated Test Post')
        self.assertEqual(self.post.content, 'Updated Test content')

class TestPostDeleteView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')

    def test_post_delete_view(self):
        response = self.client.post(reverse('posts:post-delete', args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 0)

class TestStreamView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post1 = Post.objects.create(user=self.user, question_text='Test Post 1', content='Test content 1')
        self.post2 = Post.objects.create(user=self.user, question_text='Test Post 2', content='Test content 2')
        Stream.objects.create(user=self.user, post=self.post1, following=self.user)
        Stream.objects.create(user=self.user, post=self.post2, following=self.user)

    def test_stream_view(self):
        response = self.client.get(reverse('posts:stream'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/stream.html')
        self.assertContains(response, self.post1.question_text)
        self.assertContains(response, self.post2.question_text)

class TestUserFavoritesList(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post1 = Post.objects.create(user=self.user, question_text='Test Post 1', content='Test content 1')
        self.post2 = Post.objects.create(user=self.user, question_text='Test Post 2', content='Test content 2')
        self.user.profile.favorite.add(self.post1)
        self.user.profile.favorite.add(self.post2)

    def test_user_favorites_list(self):
        response = self.client.get(reverse('posts:user-favorites', args=[self.user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/profile_favorites.html')
        self.assertContains(response, self.post1.question_text)
        self.assertContains(response, self.post2.question_text)

class TestLikeView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')

    def test_like_view(self):
        response = self.client.get(reverse('posts:like', args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Like.objects.count(), 1)
        self.assertEqual(self.post.likes, 1)

class TestFavoritesView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')

    def test_favorites_view(self):
        response = self.client.get(reverse('posts:favorites', args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.profile.favorite.count(), 1)

class TestFollowView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.following = User.objects.create_user(username='following', password='followingpass')

    def test_follow_view(self):
        response = self.client.get(reverse('posts:follow', args=[self.following.username, 1]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Follow.objects.count(), 1)

class TestTagCreationView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)

    def test_tag_creation_view(self):
        response = self.client.post(reverse('posts:tag-create'), {'title': 'Test Tag'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tag.objects.count(), 1)

class TestHtmxDomePostsView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.dome = Dome.objects.create(name='Test Dome', user=self.user)
        self.post1 = Post.objects.create(user=self.user, question_text='Test Post 1', content='Test content 1', dome=self.dome)
        self.post2 = Post.objects.create(user=self.user, question_text='Test Post 2', content='Test content 2', dome=self.dome)

    def test_htmxdome_posts_view(self):
        response = self.client.get(reverse('posts:dome-posts', args=[self.dome.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'Domes/dome_detail_posts.html')
        self.assertContains(response, self.post1.question_text)
        self.assertContains(response, self.post2.question_text)

class TestRepliesListView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        self.post = Post.objects.create(user=self.user, question_text='Test Post', content='Test content')
        self.comment1 = Comment.objects.create(post=self.post, user=self.user, comment='Test Comment 1')
        self.comment2 = Comment.objects.create(post=self.post, user=self.user, comment='Test Comment 2', reply_to=self.comment1)

    def test_replies_list_view(self):
        response = self.client.get(reverse('posts:comment-replies', args=[self.comment1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'posts/replies_list.html')
        self.assertContains(response, self.comment2.comment)