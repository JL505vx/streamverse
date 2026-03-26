from pathlib import Path
from difflib import SequenceMatcher

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.text import slugify

from core.models import UserProfile
from core.supabase_storage import upload_local_file
from movies.models import Movie


class Command(BaseCommand):
    help = 'Migra archivos legacy de media/ a Supabase Storage antes de eliminar columnas FileField.'

    def handle(self, *args, **options):
        media_root = Path(settings.BASE_DIR) / 'media'
        if not media_root.exists():
            self.stdout.write(self.style.WARNING('No existe la carpeta media/. No hay archivos legacy que migrar.'))
            return

        covers_dir = media_root / 'covers'
        videos_dir = media_root / 'videos'
        avatars_dir = media_root / 'avatars'

        movie_cover_column = self._column_exists('movies_movie', 'cover_file')
        movie_video_column = self._column_exists('movies_movie', 'video_file')
        avatar_column = self._column_exists('core_userprofile', 'avatar_file')

        migrated = 0

        if movie_cover_column or movie_video_column:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, cover_file, video_file FROM movies_movie')
                movie_rows = cursor.fetchall()

            for movie_id, cover_file, video_file in movie_rows:
                movie = Movie.objects.get(pk=movie_id)
                updated_fields = []

                if movie_cover_column and cover_file and not movie.cover_url:
                    local_path = media_root / str(cover_file)
                    if local_path.exists():
                        movie.cover_url = upload_local_file(local_path, folder='covers')
                        local_path.unlink(missing_ok=True)
                        updated_fields.append('cover_url')

                if movie_video_column and video_file and not movie.video_url:
                    local_path = media_root / str(video_file)
                    if local_path.exists():
                        movie.video_url = upload_local_file(local_path, folder='videos')
                        local_path.unlink(missing_ok=True)
                        updated_fields.append('video_url')

                if updated_fields:
                    movie.save(update_fields=updated_fields)
                    migrated += 1

        for movie in Movie.objects.all():
            updated_fields = []

            if not movie.cover_url and covers_dir.exists():
                matched_cover = self._match_file(movie.title, covers_dir.iterdir())
                if matched_cover:
                    movie.cover_url = upload_local_file(matched_cover, folder='covers')
                    matched_cover.unlink(missing_ok=True)
                    updated_fields.append('cover_url')

            if not movie.video_url and videos_dir.exists():
                matched_video = self._match_file(movie.title, videos_dir.iterdir())
                if matched_video:
                    movie.video_url = upload_local_file(matched_video, folder='videos')
                    matched_video.unlink(missing_ok=True)
                    updated_fields.append('video_url')

            if updated_fields:
                movie.save(update_fields=updated_fields)
                migrated += 1

        if avatar_column:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, avatar_file FROM core_userprofile')
                profile_rows = cursor.fetchall()

            for profile_id, avatar_file in profile_rows:
                if not avatar_file:
                    continue
                profile = UserProfile.objects.get(pk=profile_id)
                if profile.avatar_url:
                    continue
                local_path = media_root / str(avatar_file)
                if not local_path.exists():
                    continue
                profile.avatar_url = upload_local_file(local_path, folder='avatars')
                profile.save(update_fields=['avatar_url'])
                local_path.unlink(missing_ok=True)
                migrated += 1

        if avatars_dir.exists():
            for profile in UserProfile.objects.filter(avatar_url=''):
                matched_avatar = self._match_file(profile.display_name or profile.user.username, avatars_dir.iterdir())
                if not matched_avatar:
                    continue
                profile.avatar_url = upload_local_file(matched_avatar, folder='avatars')
                profile.save(update_fields=['avatar_url'])
                matched_avatar.unlink(missing_ok=True)
                migrated += 1

        self.stdout.write(self.style.SUCCESS(f'Migracion legacy completada. Registros actualizados: {migrated}'))

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table_name)
        return any(column.name == column_name for column in description)

    def _match_file(self, title: str, files) -> Path | None:
        files = [file for file in files if file.is_file()]
        if not files:
            return None

        target = self._normalize(title)
        best_path = None
        best_score = 0.0

        for file_path in files:
            current = self._normalize(file_path.stem)
            score = SequenceMatcher(None, target, current).ratio()
            if target in current or current in target:
                score += 0.2
            if score > best_score:
                best_score = score
                best_path = file_path

        if best_score >= 0.6:
            return best_path
        return None

    def _normalize(self, value: str) -> str:
        return (slugify(value or '') or '').replace('-', '')
