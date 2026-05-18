from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
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
]