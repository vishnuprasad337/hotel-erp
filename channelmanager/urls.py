from django.urls import path
from . import views


urlpatterns = [

    # ================================================================
    # WEBSITE CHANNELS
    # ================================================================

    path(
        "website/",
        views.WebsiteChannelListView.as_view(),
        name="website-channel-list",
    ),

    path(
        "website/<int:pk>/",
        views.WebsiteChannelDetailView.as_view(),
        name="website-channel-detail",
    ),

    path(
        "website/<int:pk>/toggle/",
        views.WebsiteChannelToggleView.as_view(),
        name="website-channel-toggle",
    ),

    path(
        "website/<int:pk>/sync/",
        views.WebsiteChannelSyncView.as_view(),
        name="website-channel-sync",
    ),

    path(
        "website/<int:pk>/rotate-key/",
        views.WebsiteChannelRotateKeyView.as_view(),
        name="website-channel-rotate-key",
    ),


    # ================================================================
    # WEBSITE CONNECTION HANDSHAKE
    # ================================================================

    path(
        "connect-response/",
        views.WebsiteConnectResponseView.as_view(),
        name="website-connect-response",
    ),


    # ================================================================
    # WEBSITE WEBHOOK
    # ================================================================

    path(
        "webhook/<str:api_key>/",
        views.WebhookReceiveView.as_view(),
        name="webhook-receive",
    ),


    # ================================================================
    # OTA CHANNELS
    # ================================================================

    # List all OTA channels
    path(
        "ota/",
        views.OTAChannelListView.as_view(),
        name="ota-channel-list",
    ),

    # OTA channel details
    path(
        "ota/<int:pk>/",
        views.OTAChannelDetailView.as_view(),
        name="ota-channel-detail",
    ),

    # Enable / disable OTA channel
    path(
        "ota/<int:pk>/toggle/",
        views.OTAChannelToggleView.as_view(),
        name="ota-channel-toggle",
    ),

    # Test OTA connection
    path(
        "ota/<int:pk>/check/",
        views.OTAChannelCheckView.as_view(),
        name="ota-channel-check",
    ),


    # ================================================================
    # OTA ROOM MAPPINGS
    # ================================================================

    # List/create mappings for a channel
    path(
        "ota/<int:pk>/mappings/",
        views.OTARoomMappingView.as_view(),
        name="ota-channel-mappings",
    ),

    # Delete individual OTA room mapping
    path(
        "ota-mappings/<int:pk>/",
        views.OTARoomMappingDeleteView.as_view(),
        name="ota-mapping-delete",
    ),


    # ================================================================
    # OTA WEBHOOK
    # ================================================================

    path(
        "ota-webhook/<int:channel_id>/",
        views.OTAWebhookReceiveView.as_view(),
        name="ota-webhook-receive",
    ),


    # ================================================================
    # iCAL FEED
    # ================================================================

    path(
        "ical/<str:hotel_token>/",
        views.ICalFeedView.as_view(),
        name="ical-feed",
    ),


    # ================================================================
    # LOG APIs
    # ================================================================

    # Incoming webhook events
    path(
        "webhook-events/",
        views.WebhookEventListView.as_view(),
        name="webhook-event-list",
    ),

    # Channel synchronization logs
    path(
        "sync-logs/",
        views.SyncLogListView.as_view(),
        name="sync-log-list",
    ),


    # ================================================================
    # CHANNEL MANAGER PAGES
    # ================================================================

    # Main Channel Manager
    path(
        "manager/",
        views.channel_manager_page,
        name="channel-manager",
    ),

    # Website Channels page
    path(
        "website-channels/",
        views.website_channels_page,
        name="website-channels-page",
    ),

    # OTA Channels page
    path(
        "ota-channels/",
        views.ota_channels_page,
        name="ota-channels-page",
    ),

    # Sync Logs page
    path(
        "sync-logs-page/",
        views.sync_logs_page,
        name="sync-logs-page",
    ),

    # Webhook Events page
    path(
        "webhook-events-page/",
        views.webhook_events_page,
        name="webhook-events-page",
    ),
]