from django.urls import path
from . import views

urlpatterns = [
    # ── Website Channels ──────────────────────────────────────────────────
    path("website/",                     views.WebsiteChannelListView.as_view(),      name="website-channel-list"),
    path("website/<int:pk>/",            views.WebsiteChannelDetailView.as_view(),    name="website-channel-detail"),
    path("website/<int:pk>/toggle/",     views.WebsiteChannelToggleView.as_view(),    name="website-channel-toggle"),
    path("website/<int:pk>/sync/",       views.WebsiteChannelSyncView.as_view(),      name="website-channel-sync"),
    path("website/<int:pk>/rotate-key/", views.WebsiteChannelRotateKeyView.as_view(), name="website-channel-rotate-key"),

    # ── Connection handshake ──────────────────────────────────────────────
    path("connect-response/",            views.WebsiteConnectResponseView.as_view(),  name="website-connect-response"),

    # ── Webhook — schema in URL so no subdomain needed ────────────────────
    path("webhook/<str:api_key>/",       views.WebhookReceiveView.as_view(),          name="webhook-receive"),

    # ── OTA Channels ──────────────────────────────────────────────────────
    path("ota/",                         views.OTAChannelListView.as_view(),          name="ota-channel-list"),
    path("ota/<int:pk>/",                views.OTAChannelDetailView.as_view(),        name="ota-channel-detail"),
    path("ota/<int:pk>/toggle/",         views.OTAChannelToggleView.as_view(),        name="ota-channel-toggle"),

    # ── Logs ──────────────────────────────────────────────────────────────
    path("webhook-events/",              views.WebhookEventListView.as_view(),        name="webhook-event-list"),
    path("sync-logs/",                   views.SyncLogListView.as_view(),             name="sync-log-list"),
]