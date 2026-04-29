# Generated for HLS multi-bitrate quality metadata

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0011_movie_processing_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='video_original_width',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='movie',
            name='video_original_height',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='movie',
            name='video_available_qualities',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='movie',
            name='video_default_quality',
            field=models.CharField(blank=True, default='', max_length=12),
        ),
    ]
