import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from config.env_utils import build_csrf_trusted_origins
from core.forms import MovieMediaForm
from movies.models import Genre, Movie


class CsrfTrustedOriginsTests(SimpleTestCase):
    def test_builds_explicit_and_allowed_host_origins(self):
        origins = build_csrf_trusted_origins(
            ['192.168.0.144:8011', 'https://streamverse.example.com'],
            ['127.0.0.1', 'localhost'],
        )

        self.assertIn('http://192.168.0.144:8011', origins)
        self.assertIn('https://streamverse.example.com', origins)
        self.assertIn('http://127.0.0.1', origins)
        self.assertIn('https://localhost', origins)

    def test_supports_wildcard_hosts(self):
        origins = build_csrf_trusted_origins([], ['.streamverse.test'])

        self.assertIn('http://*.streamverse.test', origins)
        self.assertIn('https://*.streamverse.test', origins)


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.common_headers = {
            'HTTP_HOST': '127.0.0.1:8000',
            'HTTP_ORIGIN': 'http://127.0.0.1:8000',
        }
        self.admin_user = User.objects.create_user(
            username='adminspec',
            password='secret12345',
            is_staff=True,
            is_superuser=True,
        )
        self.user = User.objects.create_user(
            username='userspec',
            password='secret12345',
        )

    def login_admin(self):
        login_page = self.client.get(reverse('admin_login'), HTTP_HOST='127.0.0.1:8000')
        csrf_cookie = self.client.cookies['admin_csrftoken'].value
        response = self.client.post(
            reverse('admin_login'),
            {
                'username': self.admin_user.username,
                'password': 'secret12345',
                'auth_scope': 'admin',
                'csrfmiddlewaretoken': csrf_cookie,
            },
            **self.common_headers,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('admin_panel'))

    def login_user(self):
        login_page = self.client.get(reverse('login'), HTTP_HOST='127.0.0.1:8000')
        csrf_cookie = self.client.cookies['user_csrftoken'].value
        response = self.client.post(
            reverse('login'),
            {
                'username': self.user.username,
                'password': 'secret12345',
                'auth_scope': 'user',
                'csrfmiddlewaretoken': csrf_cookie,
            },
            **self.common_headers,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('user_dashboard'))

    def test_admin_panel_uses_admin_logout_route(self):
        self.login_admin()

        response = self.client.get(reverse('admin_panel'), HTTP_HOST='127.0.0.1:8000')

        self.assertContains(response, f'action="{reverse("admin_logout")}"')
        self.assertNotContains(response, f'action="{reverse("logout")}"', html=False)

    def test_admin_logout_accepts_admin_csrf_token(self):
        self.login_admin()
        csrf_cookie = self.client.cookies['admin_csrftoken'].value

        response = self.client.post(
            reverse('admin_logout'),
            {
                'auth_scope': 'admin',
                'csrfmiddlewaretoken': csrf_cookie,
            },
            **self.common_headers,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('home'))

    def test_csrf_failure_uses_friendly_template(self):
        self.login_admin()

        response = self.client.post(
            reverse('admin_logout'),
            {
                'auth_scope': 'admin',
                'csrfmiddlewaretoken': 'token-invalido',
            },
            **self.common_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/csrf_failure.html')
        self.assertContains(response, 'No pudimos validar esta solicitud', status_code=403)
        self.assertNotContains(response, 'Forbidden (403)', status_code=403)

    def test_user_dashboard_keeps_regular_logout_route(self):
        self.login_user()

        response = self.client.get(reverse('user_dashboard'), HTTP_HOST='127.0.0.1:8000')

        self.assertContains(response, f'action="{reverse("logout")}"')


class LocalVideoStatusTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.common_headers = {
            'HTTP_HOST': '127.0.0.1:8000',
            'HTTP_ORIGIN': 'http://127.0.0.1:8000',
        }
        self.genre = Genre.objects.create(name='Animacion')
        self.admin_user = User.objects.create_user(
            username='catalogadmin',
            password='secret12345',
            is_staff=True,
            is_superuser=True,
        )

    def login_admin(self):
        self.client.get(reverse('admin_login'), HTTP_HOST='127.0.0.1:8000')
        csrf_cookie = self.client.cookies['admin_csrftoken'].value
        response = self.client.post(
            reverse('admin_login'),
            {
                'username': self.admin_user.username,
                'password': 'secret12345',
                'auth_scope': 'admin',
                'csrfmiddlewaretoken': csrf_cookie,
            },
            **self.common_headers,
        )
        self.assertEqual(response.status_code, 302)

    def test_movie_marks_missing_local_video_when_file_does_not_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, MEDIA_URL='/media/'):
                movie = Movie.objects.create(
                    title='Valiente',
                    genre=self.genre,
                    release_year=2012,
                    video_url='/media/videos/valiente.mp4',
                )

                self.assertTrue(movie.video_is_local)
                self.assertFalse(movie.video_file_exists)
                self.assertEqual(movie.video_storage_label, 'Archivo local faltante')
                self.assertEqual(movie.local_video_path, str(Path(temp_dir) / 'videos' / 'valiente.mp4'))

    def test_admin_missing_video_filter_includes_broken_local_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, MEDIA_URL='/media/'):
                missing_movie = Movie.objects.create(
                    title='Valiente',
                    genre=self.genre,
                    release_year=2012,
                    video_url='/media/videos/valiente.mp4',
                )
                playable_path = Path(temp_dir) / 'videos'
                playable_path.mkdir(parents=True, exist_ok=True)
                (playable_path / 'tarzan.mp4').write_bytes(b'video')
                Movie.objects.create(
                    title='Tarzan',
                    genre=self.genre,
                    release_year=1999,
                    video_url='/media/videos/tarzan.mp4',
                )

                self.login_admin()
                response = self.client.get(reverse('admin_movies') + '?missing_video=1', HTTP_HOST='127.0.0.1:8000')

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['missing_video_count'], 1)
                self.assertContains(response, missing_movie.title)
                self.assertNotContains(response, 'Tarzan')

    def test_upload_chunk_endpoint_assembles_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, MEDIA_URL='/media/'):
                self.login_admin()
                upload_id = 'chunk-upload-test'
                filename = 'valiente.mp4'
                csrf_cookie = self.client.cookies['admin_csrftoken'].value

                response = self.client.post(
                    reverse('upload_chunk'),
                    {
                        'file': SimpleUploadedFile('chunk-0.part', b'abc123'),
                        'chunk': '0',
                        'filename': filename,
                        'total_chunks': '2',
                        'upload_id': upload_id,
                    },
                    HTTP_X_CSRFTOKEN=csrf_cookie,
                    **self.common_headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertJSONEqual(response.content, {'ok': True, 'chunk': 0, 'complete': False, 'video_url': ''})

                response = self.client.post(
                    reverse('upload_chunk'),
                    {
                        'file': SimpleUploadedFile('chunk-1.part', b'def456'),
                        'chunk': '1',
                        'filename': filename,
                        'total_chunks': '2',
                        'upload_id': upload_id,
                    },
                    HTTP_X_CSRFTOKEN=csrf_cookie,
                    **self.common_headers,
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload['ok'])
                self.assertTrue(payload['complete'])
                self.assertTrue(payload['video_url'].startswith('/media/videos/'))

                final_path = Path(temp_dir) / payload['video_url'].removeprefix('/media/')
                self.assertTrue(final_path.exists())
                self.assertEqual(final_path.read_bytes(), b'abc123def456')

    def test_movie_media_form_replaces_old_local_video_when_video_url_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, MEDIA_URL='/media/'):
                videos_dir = Path(temp_dir) / 'videos'
                videos_dir.mkdir(parents=True, exist_ok=True)
                old_file = videos_dir / 'viejo.mp4'
                old_file.write_bytes(b'old-video')

                movie = Movie.objects.create(
                    title='Valiente',
                    genre=self.genre,
                    release_year=2012,
                    video_url='/media/videos/viejo.mp4',
                )

                form = MovieMediaForm(
                    data={
                        'cover_url': '',
                        'video_url': '/media/videos/nuevo.mp4',
                    },
                    instance=movie,
                )

                self.assertTrue(form.is_valid(), form.errors)
                updated_movie = form.save()

                self.assertEqual(updated_movie.video_url, '/media/videos/nuevo.mp4')
                self.assertFalse(old_file.exists())

    def test_movie_media_form_saves_chunk_upload_metadata(self):
        movie = Movie.objects.create(
            title='Valiente',
            genre=self.genre,
            release_year=2012,
            video_url='',
        )

        form = MovieMediaForm(
            data={
                'cover_url': '',
                'video_url': '/media/videos/valiente-final.mp4',
                'chunk_upload_completed': '1',
                'chunk_upload_duration_ms': '90500',
                'chunk_upload_filename': 'Valiente Final.mp4',
                'chunk_upload_size_bytes': str(734003200),
            },
            instance=movie,
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated_movie = form.save()

        self.assertEqual(updated_movie.video_url, '/media/videos/valiente-final.mp4')
        self.assertEqual(updated_movie.video_upload_filename, 'Valiente Final.mp4')
        self.assertEqual(updated_movie.video_upload_size_bytes, 734003200)
        self.assertEqual(updated_movie.video_upload_duration_ms, 90500)
        self.assertIsNotNone(updated_movie.video_uploaded_at)

    def test_movie_media_form_clears_upload_metadata_for_external_video_url(self):
        movie = Movie.objects.create(
            title='Valiente',
            genre=self.genre,
            release_year=2012,
            video_url='/media/videos/valiente-final.mp4',
            video_upload_filename='Valiente Final.mp4',
            video_upload_size_bytes=734003200,
            video_upload_duration_ms=90500,
        )

        form = MovieMediaForm(
            data={
                'cover_url': '',
                'video_url': 'https://cdn.example.com/valiente-final.mp4',
            },
            instance=movie,
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated_movie = form.save()

        self.assertEqual(updated_movie.video_url, 'https://cdn.example.com/valiente-final.mp4')
        self.assertEqual(updated_movie.video_upload_filename, '')
        self.assertEqual(updated_movie.video_upload_size_bytes, 0)
        self.assertEqual(updated_movie.video_upload_duration_ms, 0)
        self.assertIsNone(updated_movie.video_uploaded_at)
