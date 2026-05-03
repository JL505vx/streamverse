# Generated for video timeline thumbnail previews

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0012_movie_video_quality_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='thumbnail_sprite',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='movie',
            name='thumbnail_vtt',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='movie',
            name='thumbnail_interval',
            field=models.PositiveIntegerField(default=5),
        ),
    ]
