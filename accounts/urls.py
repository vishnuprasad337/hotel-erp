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
        path('setup/', hotel_setup, name='hotel_setup'),
        
   
    path('add-amenity/',                        add_amenity,            name='add_amenity'),
    path('delete-amenity/<int:amenity_id>/',    delete_amenity,         name='delete_amenity'),
    path('get-hotel-modules/<int:hotel_id>/', get_hotel_modules, name='get_hotel_modules'),
    # Plans
    path('get-plans/',                          get_plans,              name='get_plans'),
    path('create-plan/',                        create_plan,            name='create_plan'),
    path('delete-plan/<int:plan_id>/',          delete_plan,            name='delete_plan'),
    path('update-plan-modules/<int:plan_id>/',  update_plan_modules,    name='update_plan_modules'),
   
    path('upgrade-hotel-plan/<int:hotel_id>/', upgrade_hotel_plan, name='upgrade_hotel_plan'),
    # Payments
    path('get-payments/',                       get_payments,           name='get_payments'),
    path('create-payment/',                     create_payment,         name='create_payment'),
    path('mark-payment-paid/<int:payment_id>/', mark_payment_paid,      name='mark_payment_paid'),
    path('cancel-payment/<int:payment_id>/',    cancel_payment,         name='cancel_payment'),
   path('superadmin/subscription/summary/',                hotel_subscription_summary,  name='hotel_subscription_summary'),

path('superadmin/trial/grant/<int:hotel_id>/',          grant_trial,                 name='grant_trial'),
path('superadmin/trial/revoke/<int:hotel_id>/',         revoke_trial_eligibility,    name='revoke_trial_eligibility'),
path('superadmin/trial/restore/<int:hotel_id>/',        restore_trial_eligibility,   name='restore_trial_eligibility'),
path('superadmin/trial/end/<int:hotel_id>/',            end_trial_now,               name='end_trial_now'),
path('get-staff-details/<int:staff_id>/', get_staff_details, name='get_staff_details'),
path('superadmin/subscription/status/<int:hotel_id>/',  set_subscription_status,     name='set_subscription_status'),
path('superadmin/subscription/upgrade/<int:hotel_id>/', upgrade_hotel_plan,          name='upgrade_hotel_plan'),
 path('staff/upload-id-proof/', upload_staff_id_proof, name='upload_staff_id_proof'),
path('hotel/start-trial/',                              hotel_start_trial,           name='hotel_start_trial'),
path('superadmin/trial/days/<int:hotel_id>/',           set_hotel_trial_days,        name='set_hotel_trial_days'),
 path(
        "superadmin/hotels/modules/overview/",
        get_all_hotels_modules,
        name="get_all_hotels_modules",
    ),
 path(
        "superadmin/hotels/<int:hotel_id>/set-expiry/",
        set_subscription_expiry,
        name="set_subscription_expiry",
    ),
path('start-trial/', hotel_start_trial, name='hotel_start_trial'),  
path('superadmin/hotel/<int:hotel_id>/send-mail/', send_hotel_mail, name='send_hotel_mail'),
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

 
 

