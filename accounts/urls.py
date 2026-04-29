from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
urlpatterns =[
    # ADMIN
    path("superadmin/", admin_login, name="admin_login"),
    path("superadmin/dashboard/", superuser_dashboard, name="superuser_dashboard"),
    path("approve-hotel/<int:id>/", approve_hotel, name="approve_hotel"),
    path("reject-hotel/<int:id>/", reject_hotel, name="reject_hotel"),
    path('save-hotel-modules/<int:hotel_id>/',save_hotel_modules, name='save_hotel_modules'),
     path("register/", hotel_register, name="hotel_register"),
    path("login/", hotel_login, name="hotel_login"),
     path('save-selected-amenities/', save_selected_amenities, name='save_selected_amenities'),
    path("dashboard/", dashboard, name="dashboard"),
    path('hotel/update-profile/', update_hotel_profile, name='update_hotel_profile'),
    path('amenities/', amenities_page, name='amenities_page'),
    path('add-amenity/', add_amenity, name='add_amenity'),
      path('get-amenities/',get_amenities, name='get_amenities'),
      path("delete-amenity/<int:amenity_id>/", delete_amenity, name="delete_amenity"),
      path("add-department/", add_department, name="add_department"),
      path("get-departments/", get_departments, name="get_departments"),
      path('delete-department/<int:dept_id>/', delete_department, name='delete_department'),
      path('add-permission/', add_permission, name='add_permission'),
      path('get-permissions/', get_permissions, name='get_permissions'),
      path('delete-permission/<int:perm_id>/', delete_permission, name='delete_permission'),
    path('assign-permission/',assign_permission, name='assign_permission'),
   
    # staff authentication
    path("add-staff/", staff_register, name="staff_register"),
    path('get-staff/', get_staff, name='get_staff'),
     path('update-staff/', update_staff, name='update_staff'),
     path('delete-staff/', delete_staff, name='delete_staff'),
     
      path("staff-login/", staff_login, name="staff_login"),
      path('logout/', logout_view, name='logout'),
        path('staff-logout/', staff_logout, name='staff_logout'),

    
    
    # forgot password

    

      path('password-reset/',
     auth_views.PasswordResetView.as_view(
         template_name='auth/password_reset_form.html',
         success_url='/password-reset/',
         extra_context={'show_message': True}  
     ),
     name='password_reset'),

    
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html',
             success_url='/reset/done/'
         ),
         name='password_reset_confirm'),


    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='auth/password_reset_confirm.html'
         ),
         name='password_reset_complete'),
]

 
 

