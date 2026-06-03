from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
from .api_views import (
    AmenityListAPIView, AmenityDetailAPIView,
    TaskListAPIView, TaskDetailAPIView,
    ShiftTemplateListAPIView, ShiftTemplateDetailAPIView,
    ShiftListAPIView, ShiftDetailAPIView,
    InventoryItemListAPIView, InventoryItemDetailAPIView,
    AttendanceListAPIView, AttendanceDetailAPIView,
    LeaveRequestListAPIView, LeaveRequestDetailAPIView,
    PayrollListAPIView, PayrollDetailAPIView,
    EmployeeFinancialAccountAPIView,
    FinalSettlementListAPIView, FinalSettlementDetailAPIView,
    MessageThreadListAPIView, MessageThreadDetailAPIView,
    MessageListAPIView, MessageDetailAPIView,
    ReactionAPIView,
    PinnedMessageListAPIView,
    StarredMessageListAPIView,
    PollAPIView, PollVoteAPIView,
    NotificationListAPIView, NotificationMarkReadAPIView,)
urlpatterns =[
    
    path("", index, name="index"),
   
    
     
    path("staff/", staff_page, name="staff_page"),
     
    
     
    
      path('update-staff-profile/', update_staff_profile, name='update_staff_profile'),
    
    path("assign-task/", assign_task, name="assign_task"),
    path("get-tasks/", get_tasks, name="get_tasks"),
     
     path("gets-inventory/", gets_inventory, name="gets_inventory"),

    
    
    path("assign-shift/", assign_shift, name="assign_shift"),
    path("update-shift/", update_shift, name="update_shift"),
     path('weekly-schedule/', weekly_schedule, name='weekly_schedule'),
    path("get-shifts/", get_shifts, name="get_shifts"),
    path("staff-by-shift/", staff_by_shift, name="staff_by_shift"),
    path("shift-templates/",      get_shift_templates, name="get_shift_templates"),
    path("shift-templates/save/", save_shift_template, name="save_shift_template"),
    path("delete-shift/",         delete_shift,        name="delete_shift"),
    # STAFF LOGIN
   
    # DASHBOARDS
    path("housekeeping/", housekeeping_dashboard, name="housekeeping_dashboard"),
    path("hr/", hr_dashboard, name="hr_dashboard"),
    
    path('api/start-cleaning/', start_cleaning, name='start_cleaning'),
    path('api/complete-cleaning/', complete_cleaning, name='complete_cleaning'),
    path('api/add-inventory/', add_inventory, name='add_inventory'),
    path("api/get-inventory/", get_inventory, name="get_inventory"),

    path('api/update-inventory/<int:item_id>/', update_inventory, name='update_inventory'),
    path('api/delete-inventory/<int:item_id>/', delete_inventory, name='delete_inventory'),
   # Hr Dashboaed
   path('attendance/mark/', mark_attendance, name='mark_attendance'),
    path('attendance/live/', live_attendance, name='live_attendance'),
    path('attendance/daily/', daily_report, name='daily_report'),
    path('attendance/monthly/', monthly_report, name='monthly_report'),
    path("leave/update/<int:leave_id>/", update_leave_status, name="update_leave_status"),
    path("leave/requests/", leave_requests, name="leave_requests"),
    path("leave/apply/", apply_leave, name="apply_leave"),
    path('dashboard/leave/requests/',              admin_leave_requests, name='admin_leave_requests'),
path('dashboard/leave/update/<int:leave_id>/', admin_leave_update,   name='admin_leave_update'),
   path('payroll/generate/',                     generate_payroll),
     path('payroll/dashboard/',                    payroll_dashboard),
     path('payroll/update/<int:payroll_id>/',      update_payroll),
     path('payroll/mark-paid/<int:payroll_id>/',   mark_payroll_paid),
     path('payroll/payslip/<int:payroll_id>/',     payslip),
     path('payroll/payslip/<int:payroll_id>/pdf/', download_payslip_pdf),
     path('payroll/<int:payroll_id>/',                      payroll_detail),
path('payroll/<int:payroll_id>/line-items/',           payroll_line_items),
path('payroll/line-items/<int:item_id>/',              payroll_line_item_detail),
path('payroll/<int:payroll_id>/recalculate/',          recalculate_payroll),
path('payroll/staff/<int:staff_id>/history/',          staff_payroll_history),
path('payroll/staff/<int:staff_id>/financial-account/', financial_account),
path('payroll/monthly-summary/',                       hotel_monthly_summary),
path('payroll/export/csv/',                            payroll_export_csv),
path('payroll/settlements/',                           final_settlements),
path('payroll/settlements/<int:settlement_id>/',       final_settlement_detail),
path('attendance/today/', today_attendance),  
path(
    "staff/attendance/",
    get_attendance,
    name="staff_attendance_dashboard"
),
path("staff/attendance/history/", get_attendance_history, name="attendance_history"),
 path(
        'email/recipients/',
        get_email_recipients,
        name='email_recipients',
    ),
    path(
        'email/send/',
        send_compose_email,
        name='email_send',
    ),

    path("staff/tasks/", staff_tasks, name="staff_tasks"),
    path("update-task-status/", update_task_status, name="update_task_status"),
     path("work-report/",     work_report,     name="work_report"),
 
   
    path("work-report/all/", work_report_all, name="work_report_all"),
    path("get-weekly-schedule/", get_weekly_schedule, name="get_weekly_schedule"),
    path('accountant/dashboard/', accountant_dashboard, name='accountant_dashboard'),
    path('accountant/revenue-api/', accountant_revenue_api, name='accountant_revenue_api'),
     path('api/accountant/collections/',                      accountant_collections_api,       name='accountant_collections_api'),
    path('api/accountant/collections/export/',               accountant_collections_export,    name='accountant_collections_export'),
    path(
    "accountant/expense/",
    expense_report_view,
    name="expense_report",
),

path(
    "accountant/expense/api/",
    expense_report_api,
    name="expense_report_api",
),

path(
    "accountant/expense/summary/",
    expense_summary_api,
    name="expense_summary_api",
),

path(
    "accountant/expense/add/",
    expense_add,
    name="expense_add",
),

path(
    "accountant/expense/<int:expense_id>/delete/",
    expense_delete,
    name="expense_delete",
),

path(
    "accountant/expense/export/",
    expense_export_csv,
    name="expense_export_csv",
),
path(
    "accountant/expense/<int:expense_id>/update/",
    expense_update,
    name="expense_update",
),

 # ── Staff list ─────────────────────────────────────────────────
    path('messages/staff-list/', StaffListView.as_view()),

    # ── Threads ────────────────────────────────────────────────────
    path('messages/threads/', ThreadListView.as_view()),
    path('messages/threads/create/', ThreadListView.as_view()),

    # Sub-resources — MUST be before threads/<int:thread_id>/
       path(
        'threads/<int:thread_id>/messages/',
        thread_messages_view,
        name='thread_messages'
    ),

    path('messages/threads/<int:thread_id>/members/', ThreadMembersView.as_view()),
    path('messages/threads/<int:thread_id>/mark-read/', MarkThreadReadView.as_view()),
    path('messages/threads/<int:thread_id>/pinned/', PinnedMessagesView.as_view()),
    path('messages/threads/<int:thread_id>/pins/<int:pin_id>/', PinMessageView.as_view()),
    path('messages/threads/<int:thread_id>/pins/', PinMessageView.as_view()),

    # Detail — LAST among threads/
    path('messages/threads/<int:thread_id>/', ThreadDetailView.as_view()),

    # ── Messages ───────────────────────────────────────────────────
    path('messages/messages/<int:msg_id>/attachments/', AttachmentUploadView.as_view()),
    path('messages/messages/<int:msg_id>/react/', ReactionView.as_view()),
    path('messages/messages/<int:msg_id>/pin/', PinMessageView.as_view()),
    path('messages/messages/<int:msg_id>/unpin/', PinMessageView.as_view()),
    path('messages/messages/<int:msg_id>/star/', StarredMessageView.as_view()),

    # Detail — LAST
    path('messages/messages/<int:msg_id>/', MessageDetailView.as_view()),

    # ── Notifications ──────────────────────────────────────────────
    path('messages/notifications/mark-all-read/', NotificationView.as_view()),
    path('messages/notifications/', NotificationView.as_view()),

    # ── Polls & misc ───────────────────────────────────────────────
    path('messages/starred/', StarredMessageView.as_view()),
    path('messages/polls/<int:poll_id>/vote/', PollVoteView.as_view()),
    path('messages/search/', MessageSearchView.as_view()),

    path("hotel/amenities/",                              AmenityListAPIView.as_view(),                name="amenity-list"),
    path("hotel/amenities/<int:pk>/",                     AmenityDetailAPIView.as_view(),              name="amenity-detail"),

    path("hotel/tasks/",                                  TaskListAPIView.as_view(),                   name="task-list"),
    path("hotel/tasks/<int:pk>/",                         TaskDetailAPIView.as_view(),                 name="task-detail"),

    path("hotel/shift-templates/",                        ShiftTemplateListAPIView.as_view(),          name="shift-template-list"),
    path("hotel/shift-templates/<int:pk>/",               ShiftTemplateDetailAPIView.as_view(),        name="shift-template-detail"),

    path("hotel/shifts/",                                 ShiftListAPIView.as_view(),                  name="shift-list"),
    path("hotel/shifts/<int:pk>/",                        ShiftDetailAPIView.as_view(),                name="shift-detail"),

    path("hotel/inventory/",                              InventoryItemListAPIView.as_view(),          name="inventory-list"),
    path("hotel/inventory/<int:pk>/",                     InventoryItemDetailAPIView.as_view(),        name="inventory-detail"),

    path("hotel/attendance/",                             AttendanceListAPIView.as_view(),             name="attendance-list"),
    path("hotel/attendance/<int:pk>/",                    AttendanceDetailAPIView.as_view(),           name="attendance-detail"),

    path("hotel/leave-requests/",                         LeaveRequestListAPIView.as_view(),           name="leave-request-list"),
    path("hotel/leave-requests/<int:pk>/",                LeaveRequestDetailAPIView.as_view(),         name="leave-request-detail"),

    path("hotel/payroll/",                                PayrollListAPIView.as_view(),                name="payroll-list"),
    path("hotel/payroll/<int:pk>/",                       PayrollDetailAPIView.as_view(),              name="payroll-detail"),

    path("hotel/employee-account/<int:staff_id>/",        EmployeeFinancialAccountAPIView.as_view(),   name="employee-account"),

    path("hotel/final-settlements/",                      FinalSettlementListAPIView.as_view(),        name="final-settlement-list"),
    path("hotel/final-settlements/<int:pk>/",             FinalSettlementDetailAPIView.as_view(),      name="final-settlement-detail"),

    path("hotel/threads/",                                MessageThreadListAPIView.as_view(),          name="thread-list"),
    path("hotel/threads/<int:pk>/",                       MessageThreadDetailAPIView.as_view(),        name="thread-detail"),

    path("hotel/threads/<int:thread_id>/messages/",       MessageListAPIView.as_view(),                name="message-list"),
    path("hotel/messages/<int:pk>/",                      MessageDetailAPIView.as_view(),              name="message-detail"),

    path("hotel/reactions/",                              ReactionAPIView.as_view(),                   name="reaction"),

    path("hotel/threads/<int:thread_id>/pinned/",         PinnedMessageListAPIView.as_view(),          name="pinned-messages"),

    path("hotel/starred/",                                StarredMessageListAPIView.as_view(),         name="starred-messages"),

    path("hotel/polls/",                                  PollAPIView.as_view(),                       name="poll-create"),
    path("hotel/polls/<int:pk>/",                         PollAPIView.as_view(),                       name="poll-detail"),
    path("hotel/polls/vote/",                             PollVoteAPIView.as_view(),                   name="poll-vote"),

    path("hotel/notifications/",                          NotificationListAPIView.as_view(),           name="notification-list"),
    path("hotel/notifications/<int:pk>/read/",            NotificationMarkReadAPIView.as_view(),       name="notification-mark-read"),


]