from django.contrib import admin

from .models import (
    ContentSuggestion,
    MovieRating,
    SuggestionMessage,
    UserCustomList,
    UserCustomListItem,
    UserNotification,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'autoplay_enabled')
    search_fields = ('user__username', 'display_name')


@admin.register(ContentSuggestion)
class ContentSuggestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'content_type', 'status', 'updated_at')
    list_filter = ('status', 'content_type')
    search_fields = ('title', 'user__username')


@admin.register(SuggestionMessage)
class SuggestionMessageAdmin(admin.ModelAdmin):
    list_display = ('suggestion', 'sender', 'created_at')
    search_fields = ('suggestion__title', 'sender__username', 'text')


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'title', 'is_read', 'created_at')
    list_filter = ('kind', 'is_read')
    search_fields = ('user__username', 'title', 'body')


@admin.register(UserCustomList)
class UserCustomListAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    search_fields = ('name', 'user__username')


@admin.register(UserCustomListItem)
class UserCustomListItemAdmin(admin.ModelAdmin):
    list_display = ('custom_list', 'movie', 'added_at')
    search_fields = ('custom_list__name', 'movie__title')


@admin.register(MovieRating)
class MovieRatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'score', 'updated_at')
    list_filter = ('score',)
    search_fields = ('user__username', 'movie__title', 'note')
