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
    path("payroll/generate/", generate_payroll),
   path("payroll/dashboard/",payroll_dashboard),
   path("payroll/payslip/<int:payroll_id>/",payslip),
    path("staff/tasks/", staff_tasks, name="staff_tasks"),
    path("update-task-status/", update_task_status, name="update_task_status"),
     path("work-report/",     work_report,     name="work_report"),
 
   
    path("work-report/all/", work_report_all, name="work_report_all"),
    path("get-weekly-schedule/", get_weekly_schedule, name="get_weekly_schedule")
]