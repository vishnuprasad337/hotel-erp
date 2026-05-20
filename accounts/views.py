from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from hotel.models import Staff,Room
from django.utils import timezone
import json
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from pms.models import Booking
from .models import Hotel, Department, Permission, RolePermission, Amenity, HotelModule
from .models import SubscriptionPlan,PlanPayment

from django.db import transaction

from .forms import HotelForm
from customers.models import Domain,Client


from django.shortcuts import render, redirect

from django.utils.text import slugify
from django_tenants.utils import schema_context

from .forms import HotelForm

from django.db import connection

from django_tenants.utils import schema_context, get_tenant_model


User = get_user_model()


def admin_login(request): 
    error = None

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_superuser:
                login(request, user)
                return redirect("superuser_dashboard")
            else:
                error = "Not authorized as admin"
        else:
            error = "Invalid credentials"

    return render(request, "admin/login.html", {"error": error})

def _enable_plan_modules(hotel, plan):
    with schema_context('public'):
        core_ids = list(Amenity.objects.filter(is_core=True).values_list('id', flat=True))
        plan_ids = list(plan.modules.values_list('id', flat=True))
        all_ids  = list(set(core_ids + plan_ids))

    with schema_context(hotel.schema_name):
        # Delete all non-core modules
        HotelModule.objects.filter(hotel=hotel).exclude(
            module_id__in=core_ids
        ).delete()

        # Add missing ones
        existing = set(
            HotelModule.objects.filter(hotel=hotel)
            .values_list('module_id', flat=True)
        )
        for mid in all_ids:
            if mid not in existing:
                HotelModule.objects.create(hotel=hotel, module_id=mid)


def _disable_non_core_modules(hotel):
    with schema_context('public'):
        core_ids = list(Amenity.objects.filter(is_core=True).values_list('id', flat=True))

    with schema_context(hotel.schema_name):
        HotelModule.objects.filter(hotel=hotel).exclude(
            module_id__in=core_ids
        ).delete()


def _enable_core_modules(hotel):
    with schema_context('public'):
        core_amenities = list(Amenity.objects.filter(is_core=True))

    with schema_context(hotel.schema_name):
        existing = set(
            HotelModule.objects.filter(hotel=hotel)
            .values_list('module_id', flat=True)
        )
        for amenity in core_amenities:
            if amenity.id not in existing:
                HotelModule.objects.create(hotel=hotel, module=amenity)
def _sync_statuses():
    now   = timezone.now()
    today = now.date()
 
    with schema_context('public'):
        expired_trials = list(Hotel.objects.filter(is_on_trial=True, trial_end__lt=now))
        for hotel in expired_trials:
            hotel.end_trial(reason="auto_expired")
            _disable_non_core_modules(hotel)
            try:
                send_mail(
                    subject="Your Free Trial Has Ended",
                    message=(
                        f"Hello {hotel.hotel_name},\n\n"
                        "Your free trial has ended. Please subscribe to continue.\n\n"
                        "Regards,\nAdmin Team"
                    ),
                    from_email=None,
                    recipient_list=[hotel.email],
                    fail_silently=True,
                )
            except Exception as exc:
                logger.warning("Trial-expiry email failed for %s: %s", hotel.hotel_name, exc)
 
        expired_subs = list(Hotel.objects.filter(
            subscription_status='active',
            subscription_expiry__lt=today,
        ))
        for hotel in expired_subs:
            hotel.subscription_status = 'expired'
            hotel.is_subscribed       = False
            hotel.save(update_fields=['subscription_status', 'is_subscribed'])
            _disable_non_core_modules(hotel)
 
        PlanPayment.objects.filter(
            status='pending',
            due_date__lt=today,
        ).update(status='overdue')
 

@login_required
def superuser_dashboard(request):
    if not request.user.is_superuser:
        return redirect("admin_login")
 
    _sync_statuses()
 
    with schema_context('public'):
        all_hotels     = Hotel.objects.all().order_by("-id")
        approved       = all_hotels.filter(is_approved=True)
        pending        = all_hotels.filter(is_approved=False)
        amenities      = Amenity.objects.all()
        plans          = SubscriptionPlan.objects.prefetch_related('modules').all()
 
    return render(request, "admin/dashboard.html", {
        "hotels":             all_hotels,
        "approved_hotels":    approved,
        "pending_hotel_list": pending,
        "total_hotels":       all_hotels.count(),
        "active_hotels":      approved.count(),
        "pending_hotels":     pending.count(),
        "amenities":          amenities,
        "plans":              plans,
    })
from django.core.mail import send_mail
from django.contrib import messages  
import logging

logger = logging.getLogger(__name__)

@login_required
def approve_hotel(request, id):
    if not request.user.is_superuser:
        return redirect("admin_login")

    
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=id)
        hotel.is_approved = True
        hotel.save()

    try:
        send_mail(
            subject="Hotel Approved ✅",
            message=f"""
Hello {hotel.hotel_name},

Your hotel registration has been APPROVED.

You can now login and use the system.

Regards,
Admin Team
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[hotel.email],
            fail_silently=False
        )
        messages.success(request, f"Hotel '{hotel.hotel_name}' approved and email sent.")
    except Exception as e:
        messages.warning(request, f"Hotel approved, but email failed: {e}")

    return redirect("superuser_dashboard")


@login_required
def reject_hotel(request, id):
    if not request.user.is_superuser:
        return redirect("admin_login")

    
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=id)

    reason = request.GET.get("reason", "Not meeting requirements")

    try:
        send_mail(
            subject="Hotel Rejected ❌",
            message=f"""
Hello {hotel.hotel_name},

Your hotel registration has been REJECTED.

Reason: {reason}

You can update your details and register again.

Regards,
Admin Team
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[hotel.email],
            fail_silently=False
        )
        messages.success(request, f"Rejection email sent to '{hotel.hotel_name}'.")
    except Exception as e:
        messages.warning(request, f"Hotel rejected, but email failed: {e}")

    
    with schema_context('public'):
        try:
            client = Client.objects.get(schema_name=hotel.schema_name)
            with schema_context(client.schema_name):
                Hotel.objects.filter(id=id).delete()
        except Client.DoesNotExist:
            hotel.delete()

    return redirect("superuser_dashboard")
def save_hotel_modules(request, hotel_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            module_names = data.get("modules", [])

            
            hotel = request.tenant

            amenities = Amenity.objects.filter(name__in=module_names)

            hotel.properties.set(amenities)

            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)
@require_POST
@login_required
def send_hotel_mail(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        data    = json.loads(request.body)
        subject = data.get("subject", "").strip()
        message = data.get("message", "").strip()

        if not subject or not message:
            return JsonResponse({"error": "Subject and message are required."}, status=400)

        with schema_context('public'):
            hotel = get_object_or_404(Hotel, id=hotel_id)

        send_mail(
            subject=subject,
            message=f"Hello {hotel.hotel_name},\n\n{message}\n\nRegards,\nAdmin Team",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[hotel.email],
            fail_silently=False,
        )

        return JsonResponse({"success": True, "sent_to": hotel.email})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


##----------------------Hotel Authentication----------------------
def hotel_register(request):
    if request.method == "POST":
        form = HotelForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    with schema_context('public'):
                        hotel = form.save(commit=False)
                        base_schema = slugify(hotel.hotel_name)
                        schema_name = base_schema
                        counter = 1

                        while Client.objects.filter(schema_name=schema_name).exists():
                            schema_name = f"{base_schema}{counter}"
                            counter += 1

                        client = Client.objects.create(
                            schema_name=schema_name,
                            name=hotel.hotel_name
                        )
                        hotel.schema_name = schema_name
                        hotel.save()

                        domain = Domain.objects.create(
                            tenant=client,
                            domain=f"{schema_name}.{settings.BASE_URL}",
                            is_primary=True
                        )

                    with schema_context(schema_name):
                        email = form.cleaned_data.get("email")
                        password = form.cleaned_data.get("password")

                        user = User.objects.create_user(
                            username=email,
                            email=email,
                            password=password,
                            hotel=hotel,
                        )

                
                try:
                    send_mail(
                        subject="Registration Received - Pending Approval",
                        message=f"""
Hello {hotel.hotel_name},

Thank you for registering! Your application is pending admin approval.

You will receive another email once approved.

Regards,
Admin Team
""",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[hotel.email],
                        fail_silently=False
                    )
                except Exception as e:
                    print(f"Registration email error: {e}")  

                return redirect(f"http://{domain.domain}{settings.PORT}")

            except Exception as e:
                print("ERROR:", e)
                form.add_error(None, "Something went wrong")

    return render(request, "register.html", {"tenant_form": HotelForm()})
from django.contrib.auth import update_session_auth_hash

@require_POST
def update_hotel_profile(request):
    try:
        current_tenant = connection.tenant

       
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST

       
        with schema_context('public'):
            hotel = get_object_or_404(
                Hotel,
                schema_name=current_tenant.schema_name
            )

           
            hotel.hotel_name = data.get("hotel_name", hotel.hotel_name)
            hotel.owner_name = data.get("owner_name", hotel.owner_name)
            hotel.address    = data.get("address", hotel.address)
            hotel.city       = data.get("city", hotel.city)
            hotel.property_type = data.get("property_type", hotel.property_type)
            hotel.description   = data.get("description", hotel.description)

            
            if request.FILES.get("image"):
                hotel.image = request.FILES["image"]

            email = data.get("email")
            if email:
                hotel.email = email

            hotel.save()

        
        user = request.user

        if email:
            user.email = email
            user.username = email

        
        current_password = data.get("current_password")
        new_password     = data.get("new_password")
        confirm_password = data.get("confirm_password")

        if new_password:
          
            if not current_password:
                return JsonResponse({"error": "Enter current password"}, status=400)

            if not user.check_password(current_password):
                return JsonResponse({"error": "Current password incorrect"}, status=400)

            if new_password != confirm_password:
                return JsonResponse({"error": "Passwords do not match"}, status=400)

           
            user.set_password(new_password)
            user.save()

          
            update_session_auth_hash(request, user)

        user.save()

        return JsonResponse({
            "success": True,
            "hotel_name": hotel.hotel_name,
            "email": user.email,
            "image": hotel.image.url if hotel.image else None
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



def hotel_login(request):
    error = None
    success_msg = request.GET.get("approved")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        if not email or not password:
            return render(request, "login.html", {
                "error": "Enter email and password",
                "success": success_msg
            })

        current_tenant = request.tenant

        with schema_context(current_tenant.schema_name):
            user = authenticate(request, username=email, password=password)

        if user is None:
            return render(request, "login.html", {
                "error": "Invalid credentials",
                "success": success_msg
            })

        if not user.is_active:
            return render(request, "login.html", {
                "error": "Account is disabled",
                "success": success_msg
            })

        with schema_context('public'):
            try:
                hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)
            except Hotel.DoesNotExist:
                return render(request, "login.html", {
                    "error": "Hotel not found",
                    "success": success_msg
                })

            if not hotel.is_approved:
                return render(request, "login.html", {
                    "error": "Your hotel is pending approval by admin",
                    "success": success_msg
                })

        login(request, user)

        request.session["hotel_id"] = hotel.id

        
        if not hotel.is_setup_complete:
            return redirect("hotel_setup")
        if request.GET.get("edit")=="true":
             return redirect("hotel_setup")


        return redirect("dashboard")

    return render(request, "login.html", {
        "error": error,
        "success": success_msg
    })
def amenities_page(request):
    amenities = Amenity.objects.all()
    return render(request, "amenities.html", {"amenities": amenities})













@require_POST
def save_selected_amenities(request):
    

   
    if request.content_type == 'application/json':
        data = json.loads(request.body)
        selected_ids = data.get("amenities", [])
    else:
        selected_ids = request.POST.getlist("amenities[]")
    
   
    selected_ids = [int(id) for id in selected_ids if id and str(id).isdigit()]
    
    print(f"Selected IDs: {selected_ids}")

   
    current_tenant = connection.tenant
    print(f" Current tenant schema: {current_tenant.schema_name}")
    print(f" Current tenant ID: {current_tenant.id}")

    
    with schema_context('public'):
        try:
            hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)
          
        except Hotel.DoesNotExist:
           
            return JsonResponse({"status": "error", "message": "Hotel not found"})

        
        amenities = Amenity.objects.filter(id__in=selected_ids)
        
  
    with schema_context(current_tenant.schema_name):
        
        deleted_count, _ = HotelModule.objects.filter(hotel=hotel).delete()
        print(f"Deleted old modules: {deleted_count}")

       
        created_count = 0
        for amenity in amenities:
            HotelModule.objects.create(
                hotel=hotel,
                module=amenity  
            )
            created_count += 1

        print(f"Created modules: {created_count}")

    return JsonResponse({
        "status": "success",
        "saved_count": created_count,
        "hotel": hotel.hotel_name
    })
@require_POST
def add_amenity(request):
    try:
        data        = json.loads(request.body)
        name        = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_core     = bool(data.get("is_core", False))   # ← read from request

        if not name:
            return JsonResponse({"error": "Module name is required."}, status=400)

        amenity, created = Amenity.objects.get_or_create(
            name=name,
            defaults={"description": description, "is_core": is_core}  # ← use it
        )
        if not created:
            return JsonResponse({"error": "A module with this name already exists."}, status=400)

        return JsonResponse({
            "id":          amenity.id,
            "name":        amenity.name,
            "description": amenity.description,
            "is_core":     amenity.is_core,
            "created":     True,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def get_amenities(request):
    try:
        with schema_context('public'):
            data = list(
                Amenity.objects.all().values("id", "name", "description", "is_core")
            )
        return JsonResponse({"modules": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
from django.views.decorators.http import require_POST, require_http_methods
from dateutil.relativedelta import relativedelta
from datetime import datetime
@require_http_methods(["DELETE"])
def delete_amenity(request, amenity_id):
    try:
        amenity = get_object_or_404(Amenity, id=amenity_id)
        amenity.delete()
        return JsonResponse({"success": True, "id": amenity_id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def get_plans(request):
    try:
        with schema_context('public'):
            plans = SubscriptionPlan.objects.prefetch_related('modules').all()
            data  = [
                {
                    "id":           p.id,
                    "name":         p.name,
                    "price":        str(p.price),
                    "tagline":      p.tagline or "",
                    "module_ids":   list(p.modules.values_list("id", flat=True)),
                    "module_names": list(p.modules.values_list("name", flat=True)),
                }
                for p in plans
            ]
        return JsonResponse({"plans": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@require_POST
@login_required
def hotel_start_trial(request):
    current_tenant = connection.tenant

    with schema_context('public'):
        hotel = get_object_or_404(Hotel, schema_name=current_tenant.schema_name)

        if not hotel.trial_eligible:
            return JsonResponse({"error": "Not eligible for a trial."}, status=400)

        if hotel.subscription_status in ('active', 'trial'):
            return JsonResponse({"error": "Already on trial or subscribed."}, status=400)

        # Get the plan_id if hotel wants trial on a specific plan
        data    = json.loads(request.body) if request.body else {}
        plan_id = data.get("plan_id")
        plan    = None

        if plan_id:
            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            hotel.subscription_plan = plan
            hotel.save(update_fields=['subscription_plan'])

        try:
            hotel.start_trial(granted_by="self_service")
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        if plan:
            _enable_plan_modules(hotel, plan)
        else:
            _enable_core_modules(hotel)

        hotel.refresh_from_db()

    try:
        send_mail(
            subject="Your Free Trial Has Started 🎉",
            message=(
                f"Hello {hotel.hotel_name},\n\n"
                f"Your {hotel.trial_days}-day free trial has started!\n"
                f"Plan: {plan.name if plan else 'Core modules'}\n"
                f"Trial ends: {hotel.trial_end.strftime('%d %b %Y')}\n\n"
                "Regards,\nHotelCloud Team"
            ),
            from_email=None,
            recipient_list=[hotel.email],
            fail_silently=True,
        )
    except Exception:
        pass

    return JsonResponse({
        "success":   True,
        "trial_end": hotel.trial_end.strftime("%d %b %Y"),
        "days":      hotel.trial_days,
        "plan":      plan.name if plan else "Core only",
    })
@login_required
def get_hotel_modules(request, hotel_id):
    
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    try:
        with schema_context("public"):
            hotel = get_object_or_404(Hotel, id=hotel_id)
            target_schema = hotel.schema_name
 
        with schema_context(target_schema):
            hotel_modules = (
                HotelModule.objects
                .filter(hotel=hotel)
                .select_related("module")
            )
 
            modules = [
                {
                    "id":          hm.module.id,
                    "name":        hm.module.name,
                    "description": hm.module.description or "",
                    "is_core":     hm.module.is_core,
                    "is_enabled":  hm.is_enabled,
                }
                for hm in hotel_modules
            ]
 
        return JsonResponse({
            "hotel_id":            hotel.id,
            "hotel_name":          hotel.hotel_name,
            "subscription_status": hotel.subscription_status,
            "subscription_plan":   hotel.subscription_plan.name if hotel.subscription_plan else None,
            "subscription_expiry": str(hotel.subscription_expiry) if hotel.subscription_expiry else None,
            "is_on_trial":         hotel.is_on_trial,
            "total_modules":       len(modules),
            "modules":             modules,
        })
 
    except Exception as e:
        logger.exception("get_hotel_modules failed for hotel_id=%s", hotel_id)
        return JsonResponse({"error": str(e)}, status=500)
@login_required
def get_all_hotels_modules(request):
    
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    try:
        status_filter   = request.GET.get("status", "").strip()
        core_only_param = request.GET.get("is_core_only", "").strip().lower()
 
        with schema_context("public"):
            hotels_qs = Hotel.objects.select_related("subscription_plan").order_by("hotel_name")
 
            if status_filter:
                hotels_qs = hotels_qs.filter(subscription_status=status_filter)
 
            hotels = list(hotels_qs)
 
        result = []
 
        for hotel in hotels:
            try:
                with schema_context(hotel.schema_name):
                    hotel_modules = (
                        HotelModule.objects
                        .filter(hotel=hotel, is_enabled=True)
                        .select_related("module")
                    )
 
                    modules = [
                        {
                            "id":      hm.module.id,
                            "name":    hm.module.name,
                            "is_core": hm.module.is_core,
                        }
                        for hm in hotel_modules
                    ]
 
            except Exception as schema_err:
                
                logger.warning(
                    "Could not fetch modules for hotel %s (%s): %s",
                    hotel.hotel_name, hotel.schema_name, schema_err,
                )
                modules = []
 
            core_count    = sum(1 for m in modules if m["is_core"])
            non_core_count = len(modules) - core_count
 
            
            if core_only_param == "true" and non_core_count > 0:
                continue
 
            result.append({
                "hotel_id":            hotel.id,
                "hotel_name":          hotel.hotel_name,
                "email":               hotel.email,
                "subscription_status": hotel.subscription_status,
                "subscription_plan":   hotel.subscription_plan.name if hotel.subscription_plan else None,
                "subscription_expiry": str(hotel.subscription_expiry) if hotel.subscription_expiry else None,
                "is_on_trial":         hotel.is_on_trial,
                "trial_end":           hotel.trial_end.strftime("%d %b %Y") if hotel.trial_end else None,
                "total_modules":       len(modules),
                "core_modules":        core_count,
                "non_core_modules":    non_core_count,
                "modules":             modules,
            })
 
        return JsonResponse({
            "total_hotels": len(result),
            "hotels":       result,
        })
 
    except Exception as e:
        logger.exception("get_all_hotels_modules failed")
        return JsonResponse({"error": str(e)}, status=500)
 
@require_POST
def create_plan(request):
    try:
        data  = json.loads(request.body)
        name  = data.get("name", "").strip()
        price = data.get("price", 0)

        if not name:
            return JsonResponse({"error": "Plan name is required."}, status=400)
        if SubscriptionPlan.objects.filter(name__iexact=name).exists():
            return JsonResponse({"error": "A plan with this name already exists."}, status=400)

        plan = SubscriptionPlan.objects.create(name=name, price=price)
        return JsonResponse({"success": True, "id": plan.id, "name": plan.name, "price": str(plan.price)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["DELETE"])
def delete_plan(request, plan_id):
    try:
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def update_plan_modules(request, plan_id):
    try:
        data       = json.loads(request.body)
        module_ids = data.get("module_ids", [])
        plan       = get_object_or_404(SubscriptionPlan, id=plan_id)

        amenities = Amenity.objects.filter(id__in=module_ids, is_core=False)
        plan.modules.set(amenities)

        # Sync every hotel currently on this plan
        with schema_context('public'):
            hotels_on_plan = list(Hotel.objects.filter(
                subscription_plan=plan,
                subscription_status__in=['active', 'trial']
            ))

        for hotel in hotels_on_plan:
            _enable_plan_modules(hotel, plan)

        return JsonResponse({
            "success":       True,
            "plan":          plan.name,
            "synced_hotels": len(hotels_on_plan)
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@require_POST
def save_hotel_modules(request, hotel_id):
    try:
        data = json.loads(request.body)
        module_ids = data.get("modules", [])

        with schema_context('public'):
            hotel = get_object_or_404(Hotel, id=hotel_id)
            target_schema = hotel.schema_name

            # Only allow modules that are in the hotel's current plan
            allowed_ids = set()
            if hotel.subscription_plan:
                allowed_ids = set(
                    hotel.subscription_plan.modules.values_list('id', flat=True)
                )
            # Always allow core modules
            core_ids = set(
                Amenity.objects.filter(is_core=True).values_list('id', flat=True)
            )
            allowed_ids.update(core_ids)

            
            valid_ids = [mid for mid in module_ids if int(mid) in allowed_ids]
            amenities = Amenity.objects.filter(id__in=valid_ids)

        with schema_context(target_schema):
            HotelModule.objects.filter(hotel=hotel, module__is_core=False).delete()
            for amenity in amenities:
                HotelModule.objects.get_or_create(hotel=hotel, module=amenity)

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@require_POST
def upgrade_hotel_plan(request, hotel_id):
    try:
        data    = json.loads(request.body)
        plan_id = data.get("plan_id")
        
        print("DEBUG plan_id received:", plan_id)  # ← add this

        with schema_context('public'):
            hotel = get_object_or_404(Hotel, id=hotel_id)
            plan  = get_object_or_404(SubscriptionPlan, id=plan_id)

            hotel.subscription_plan   = plan
            hotel.subscription_status = 'active'
            hotel.is_subscribed       = True
            hotel.is_on_trial         = False
            hotel.subscription_expiry = timezone.now().date() + relativedelta(months=1)
            hotel.save(update_fields=[
                'subscription_plan',
                'subscription_status',
                'is_subscribed',
                'is_on_trial',
                'subscription_expiry',
            ])
            
            hotel.refresh_from_db()
            print("DEBUG saved expiry:", hotel.subscription_expiry)  # ← add this

            _enable_plan_modules(hotel, plan)

            PlanPayment.objects.create(
                hotel    = hotel,
                plan     = plan,
                amount   = plan.price,
                status   = 'pending',
                due_date = timezone.now().date() + relativedelta(months=1),
            )

        return JsonResponse({"success": True, "hotel": hotel.hotel_name, "plan": plan.name})

    except Exception as exc:
        print("DEBUG upgrade error:", str(exc))  
        return JsonResponse({"error": str(exc)}, status=500)
def get_payments(request):
    
    try:
        with schema_context('public'):
            PlanPayment.objects.filter(
                status='pending',
                due_date__lt=timezone.now().date()
            ).update(status='overdue')

            qs = PlanPayment.objects.select_related('hotel', 'plan').all()

            status_f = request.GET.get('status')
            hotel_f  = request.GET.get('hotel_id')
            if status_f:
                qs = qs.filter(status=status_f)
            if hotel_f:
                qs = qs.filter(hotel_id=hotel_f)

            data = [
                {
                    "id":             p.id,
                    "hotel_id":       p.hotel.id,
                    "hotel_name":     p.hotel.hotel_name,
                    "plan_name":      p.plan.name if p.plan else "—",
                    "amount":         str(p.amount),
                    "status":         p.status,
                    "due_date":       str(p.due_date),
                    "paid_date":      str(p.paid_date) if p.paid_date else None,
                    "transaction_id": p.transaction_id or "",
                    "notes":          p.notes or "",
                    "created_at":     p.created_at.strftime("%d %b %Y"),
                }
                for p in qs
            ]
        return JsonResponse({"payments": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def mark_payment_paid(request, payment_id):
    try:
        data    = json.loads(request.body)
        payment = get_object_or_404(PlanPayment, id=payment_id)
 
        payment.status         = 'paid'
        payment.paid_date      = timezone.now().date()
        payment.transaction_id = data.get('transaction_id', '').strip()
        payment.notes          = data.get('notes', '').strip()
        payment.save()
 
        PlanPayment.objects.create(
            hotel    = payment.hotel,
            plan     = payment.plan,
            amount   = payment.amount,
            status   = 'pending',
            due_date = payment.due_date + relativedelta(months=1),
        )
 
        with schema_context('public'):
            hotel = payment.hotel
            hotel.subscription_expiry = (hotel.subscription_expiry or timezone.now().date()) + relativedelta(months=1)
            hotel.subscription_status = 'active'
            hotel.is_subscribed       = True
            hotel.save(update_fields=['subscription_expiry', 'subscription_status', 'is_subscribed'])
 
        return JsonResponse({"success": True})
 
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
 

@require_POST
def cancel_payment(request, payment_id):
    try:
        payment        = get_object_or_404(PlanPayment, id=payment_id)
        payment.status = 'cancelled'
        payment.save()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def create_payment(request):
    
    try:
        data    = json.loads(request.body)
        hotel   = get_object_or_404(Hotel, id=data.get('hotel_id'))
        plan    = SubscriptionPlan.objects.filter(id=data.get('plan_id')).first()

        due_date_str = data.get('due_date')
        if not due_date_str:
            return JsonResponse({"error": "Due date is required."}, status=400)

        payment = PlanPayment.objects.create(
            hotel          = hotel,
            plan           = plan,
            amount         = data.get('amount', 0),
            status         = data.get('status', 'pending'),
            due_date       = due_date_str,
            transaction_id = data.get('transaction_id', '').strip(),
            notes          = data.get('notes', '').strip(),
        )
        return JsonResponse({"success": True, "id": payment.id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
from pms.models import Room, RoomUnit
from django.views.decorators.cache import never_cache
@never_cache
@login_required
def dashboard(request):
    from pms.models import Room, RoomUnit, RoomImage
    current_tenant = connection.tenant
    _sync_statuses()

    with schema_context('public'):
        hotel = Hotel.objects.select_related('subscription_plan').get(
            schema_name=current_tenant.schema_name
        )

    print(f"\n{'='*60}")
    print(f"HOTEL: {hotel.hotel_name}")
    print(f"SCHEMA: {hotel.schema_name}")
    print(f"is_subscribed: {hotel.is_subscribed}")
    print(f"is_on_trial: {hotel.is_on_trial}")
    print(f"subscription_plan: {hotel.subscription_plan}")
    print(f"subscription_status: {hotel.subscription_status}")

    if hotel.subscription_plan:
        with schema_context('public'):
            plan_module_names = list(
                hotel.subscription_plan.modules.values_list('name', flat=True)
            )
        print(f"PLAN MODULES ({len(plan_module_names)}): {plan_module_names}")
    else:
        print("PLAN MODULES: No plan assigned")

    # Before sync
    before_modules = list(
        HotelModule.objects.filter(hotel=hotel)
        .select_related('module')
        .values_list('module__name', flat=True)
    )
    print(f"BEFORE SYNC — HotelModule records ({len(before_modules)}): {before_modules}")

    # Sync
    if hotel.subscription_plan and hotel.is_subscribed:
        print(">>> Running _enable_plan_modules (subscribed)")
        _enable_plan_modules(hotel, hotel.subscription_plan)
    elif hotel.is_on_trial and hotel.subscription_plan:
        print(">>> Running _enable_plan_modules (trial)")
        _enable_plan_modules(hotel, hotel.subscription_plan)
    elif not hotel.is_subscribed and not hotel.is_on_trial:
        print(">>> Running _disable_non_core_modules")
        _disable_non_core_modules(hotel)
    else:
        print(">>> WARNING: NO SYNC RAN — check conditions")

    # After sync
    after_modules = list(
        HotelModule.objects.filter(hotel=hotel, is_enabled=True)
        .select_related('module')
        .values_list('module__name', flat=True)
    )
    print(f"AFTER SYNC — HotelModule records ({len(after_modules)}): {after_modules}")

    # Final query with hotel filter
    modules = HotelModule.objects.select_related('module').filter(
        hotel=hotel,
        is_enabled=True
    )
    print(f"MODULES QUERYSET COUNT: {modules.count()}")
    print(f"MODULES LIST: {[m.module.name for m in modules]}")

    amenities = [m.module for m in modules]

    active_module_names = set()
    for m in modules:
        name = m.module.name.lower().strip()
        active_module_names.add(name)
        active_module_names.add(name.replace(' ', '_'))
        active_module_names.add(name.replace(' ', ''))
        active_module_names.add(name.replace('-', '_'))

    print(f"ACTIVE MODULE NAMES → TEMPLATE: {sorted(active_module_names)}")
    print(f"{'='*60}\n")

    all_units = RoomUnit.objects.all()
    total_rooms = all_units.count()
    available_rooms = all_units.filter(status="Available").count()
    occupied_rooms = all_units.filter(status="Occupied").count()
    total_staff = Staff.objects.count()
    total_bookings = Booking.objects.count()
    today = timezone.now().date()
    today_checkins = Booking.objects.filter(
        check_in=today,
        status="confirmed"
    ).count()
    today_checkouts = Booking.objects.filter(
        check_out=today,
        status="checked_in"
    ).count()
    reserved_count = Booking.objects.filter(
        status="confirmed"
    ).count()

    return render(request, "property.html", {
        "hotel": hotel,
        "amenities": amenities,
        "active_module_names": active_module_names,
        "total_rooms": total_rooms,
        "available_rooms": available_rooms,
        "occupied_rooms": occupied_rooms,
        "total_staff": total_staff,
        "total_bookings": total_bookings,
        "reserved_count": reserved_count,
        "today_checkins": today_checkins,
        "today_checkouts": today_checkouts,
    })
##----------------------Role & permissions----------------------
def add_department(request):
    if request.method == "POST":
        name = request.POST.get("name")

       
        hotel = request.session.get("hotel_id")

        if hotel:
            hotel_obj = Hotel.objects.get(id=hotel)

            Department.objects.create(
                hotel=hotel_obj,
                name=name
            )

        return redirect('staff_page')
def add_permission(request):
    if request.method == "POST":
        # Handle both JSON and form POST
        if request.content_type == "application/json":
            data = json.loads(request.body)
            name = data.get("name")
        else:
            name = request.POST.get("name") or request.POST.get("permission_name")

        if name:
            perm, created = Permission.objects.get_or_create(name=name)
            return JsonResponse({"id": perm.id, "name": perm.name, "created": created})
        return JsonResponse({"error": "Name is required"}, status=400)

    return JsonResponse({"error": "Invalid method"}, status=405)
@require_http_methods(['DELETE'])
def delete_permission(request, perm_id):
    perm = get_object_or_404(Permission, id=perm_id)
    perm.delete()
    return JsonResponse({'deleted': perm_id})
def get_permissions(request):
   
    perms = Permission.objects.all().values('id', 'name')
    return JsonResponse(list(perms), safe=False)
def assign_permission(request):
    if request.method == "POST":
        dept_id = request.POST.get("department_id")
        permission_ids = request.POST.getlist("permissions")

        department = get_object_or_404(Department, id=dept_id)

        
        RolePermission.objects.filter(role=department).delete()

        
        permissions = Permission.objects.filter(id__in=permission_ids)

        RolePermission.objects.bulk_create([
            RolePermission(role=department, permission=p)
            for p in permissions
        ])

    return redirect("staff_page")
def assign_permission(request):
    if request.method == "POST":
        # Handle both JSON and form POST
        if request.content_type == "application/json":
            data = json.loads(request.body)
            dept_id = data.get("department_id")
            permission_ids = data.get("permission_ids", [])
        else:
            dept_id = request.POST.get("department_id")
            permission_ids = request.POST.getlist("permissions")

        department = get_object_or_404(Department, id=dept_id)

       
        RolePermission.objects.filter(role=department).delete()

       
        permissions_qs = Permission.objects.filter(id__in=permission_ids)
        RolePermission.objects.bulk_create([
            RolePermission(role=department, permission=p)
            for p in permissions_qs
        ])

        assigned_names = list(permissions_qs.values_list("name", flat=True))

        
        if request.content_type == "application/json":
            return JsonResponse({
                "success": True,
                "dept_name": department.name,
                "assigned_permissions": assigned_names
            })
        return redirect("staff_page")

    return JsonResponse({"error": "Invalid method"}, status=405)
def get_departments(request):
    hotel_id = request.session.get("hotel_id")  

    if not hotel_id:
        return JsonResponse({"error": "Hotel not found in session"}, status=400)

    result = []

    departments = Department.objects.filter(hotel_id=hotel_id)

    for dept in departments:
        perm_names = list(
            RolePermission.objects.filter(role=dept)
            .values_list("permission__name", flat=True)
        )

        result.append({
            "id": dept.id,
            "name": dept.name,
            "permissions": perm_names
        })

    return JsonResponse(result, safe=False)
@require_http_methods(["DELETE"])
def delete_department(request, dept_id):
    try:
        dept = get_object_or_404(Department, id=dept_id)
        dept_name = dept.name
        dept.delete()
        return JsonResponse({"message": "Department deleted", "id": dept_id, "name": dept_name})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
##----------------------Staff authentication----------------------

@csrf_exempt
@require_POST
def staff_register(request):
    try:
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST

        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        phone = data.get("phone")
        department_id = data.get("department_id")
        salary = data.get("salary") or 0

        if not all([name, email, password]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        hotel_id = request.session.get("hotel_id")
        if not hotel_id:
            return JsonResponse({"error": "Session expired. Please login again."}, status=401)

        with schema_context('public'):
            try:
                hotel = Hotel.objects.get(id=hotel_id)
            except Hotel.DoesNotExist:
                return JsonResponse({"error": "Hotel not found"}, status=404)

        tenant_schema = hotel.schema_name
        unique_username = f"{email}_{hotel.id}"  # unique across all hotels

        with schema_context(tenant_schema):
            if User.objects.filter(username=unique_username).exists():
                return JsonResponse({"error": "User already exists in this hotel"}, status=400)

        department = None
        if department_id:
            with schema_context(tenant_schema):
                department = Department.objects.filter(id=int(department_id)).first()
                if not department:
                    return JsonResponse({"error": "Department not found"}, status=400)

        with schema_context(tenant_schema):
            user = User.objects.create_user(
                username=unique_username,  
                email=email,
                password=password,
                hotel=hotel,
                role=None
            )

            staff = Staff.objects.create(
                user=user,
                hotel=hotel,
                name=name,
                phone=phone or "",
                department=department,
                salary=salary,
            )

        try:
            send_mail(
                subject="Staff Account Created",
                message=f"""
Hello {name},

Your staff account has been created.

Login Details:
Email: {email}
Password: {password}

Please login and change your password after first login.

Regards,
Hotel Management
""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True
            )
        except Exception as e:
            print("Email error:", e)

        return JsonResponse({
            "success": True,
            "staff_id": staff.id,
            "name": staff.name,
            "department": staff.department.name if staff.department else None
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def get_staff_details(request, staff_id):
    try:
        current_tenant = connection.tenant

        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)

        with schema_context(current_tenant.schema_name):
            try:
                staff = Staff.objects.select_related('department', 'user').get(id=staff_id, hotel=hotel)
                
                # Get hotel name
                hotel_name = hotel.hotel_name if hotel else "N/A"
                
                # Build the full URL for images
                request_host = request.get_host()
                request_scheme = request.scheme
                
                photo_url = None
                if staff.photo:
                    photo_url = f"{request_scheme}://{request_host}{staff.photo.url}"
                
                id_proof_image_url = None
                if staff.id_proof_image:
                    id_proof_image_url = f"{request_scheme}://{request_host}{staff.id_proof_image.url}"
                
                # Get uploaded ID cards from StaffDocument model (if exists)
                id_cards = []
                if hasattr(staff, 'documents'):
                    for doc in staff.documents.all():
                        id_cards.append({
                            'id': doc.id,
                            'document_type': doc.document_type,
                            'url': f"{request_scheme}://{request_host}{doc.document.url}" if doc.document else None,
                            'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                        })
                
                # Also add the ID proof image if exists
                if staff.id_proof_image:
                    id_cards.append({
                        'id': staff.id,
                        'document_type': dict(staff._meta.get_field('id_proof_type').choices).get(staff.id_proof_type, 'ID Proof'),
                        'url': id_proof_image_url,
                        'uploaded_at': staff.created_at.isoformat() if staff.created_at else None,
                        'id_proof_number': staff.id_proof_number,
                    })
                
                return JsonResponse({
                    "success": True,
                    "staff": {
                        "id": staff.id,
                        "employee_id": staff.employee_id,
                        "name": staff.name,
                        "email": staff.user.email if staff.user else "",
                        "phone": staff.phone or "",
                        "department_id": staff.department.id if staff.department else None,
                        "department_name": staff.department.name if staff.department else "N/A",
                        "role": staff.user.role.name if staff.user and staff.user.role else "Staff",
                        "salary": float(staff.salary) if staff.salary else 0,
                        "joining_date": staff.joining_date.strftime("%Y-%m-%d") if staff.joining_date else None,
                        "created_at": staff.created_at.isoformat() if staff.created_at else None,
                        "is_active": staff.is_active,
                        "is_available": staff.is_available,
                        "hotel_name": hotel_name,
                        "hotel_id": hotel.id if hotel else None,
                        "photo_url": photo_url,
                        # ID proof fields
                        "id_proof_type": staff.id_proof_type,
                        "id_proof_type_label": dict(staff._meta.get_field('id_proof_type').choices).get(staff.id_proof_type, '') if staff.id_proof_type else '',
                        "id_proof_number": staff.id_proof_number,
                        "id_proof_image_url": id_proof_image_url,
                    },
                    "id_cards": id_cards
                })
                
            except Staff.DoesNotExist:
                return JsonResponse({"error": "Staff not found", "success": False}, status=404)
                
    except Hotel.DoesNotExist:
        return JsonResponse({"error": "Hotel not found", "success": False}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e), "success": False}, status=500)

@csrf_exempt
def get_staff(request):
    try:
        current_tenant = connection.tenant

        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)

        with schema_context(current_tenant.schema_name):
            staffs = Staff.objects.filter(hotel=hotel).select_related('department', 'user')

            role_permissions = RolePermission.objects.select_related('permission', 'role')

            dept_permissions_map = {}
            for rp in role_permissions:
                dept_permissions_map.setdefault(rp.role_id, []).append(rp.permission.name)

            staff_list = []

            for s in staffs:
                dept = s.department
                
                # Get hotel name from the hotel object
                hotel_name = hotel.hotel_name if hotel else "N/A"

                staff_list.append({
                    "id": s.id,
                    "employee_id": s.employee_id,
                    "name": s.name,
                    "email": s.user.email if s.user else "",
                    "phone": s.phone or "",
                    "department_id": dept.id if dept else None,
                    "department_name": dept.name if dept else "N/A",
                    "department": {
                        "id": dept.id if dept else None,
                        "name": dept.name if dept else "N/A",
                        "permissions": dept_permissions_map.get(dept.id, []) if dept else []
                    },
                    "role": s.user.role.name if s.user and s.user.role else "Staff",
                    "salary": str(s.salary),
                    "joining_date": s.joining_date.strftime("%Y-%m-%d") if s.joining_date else "",
                    "photo": s.photo.url if s.photo else None,
                    "is_active": s.is_active,
                    "is_available": s.is_available,
                    "hotel_name": hotel_name,
                    "hotel_id": hotel.id if hotel else None,
                    # New ID proof fields
                    "id_proof_type": s.id_proof_type,
                    "id_proof_type_label": dict(s._meta.get_field('id_proof_type').choices).get(s.id_proof_type, '') if s.id_proof_type else '',
                    "id_proof_number": s.id_proof_number,
                    "id_proof_image_url": s.id_proof_image.url if s.id_proof_image else None,
                })

        return JsonResponse({
            "success": True,
            "count": len(staff_list),
            "staffs": staff_list,
            "hotel_name": hotel_name  
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def upload_staff_id_proof(request):
    if request.method != 'POST':
        return JsonResponse({"error": "POST required", "success": False}, status=405)
    
    try:
        current_tenant = connection.tenant
        
        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)
        
        with schema_context(current_tenant.schema_name):
            staff_id = request.POST.get('staff_id')
            id_proof_type = request.POST.get('id_proof_type', 'other')
            id_proof_number = request.POST.get('id_proof_number', '')
            id_proof_image = request.FILES.get('id_proof_image')
            
            if not staff_id:
                return JsonResponse({"error": "Staff ID is required", "success": False}, status=400)
            
            if not id_proof_image:
                return JsonResponse({"error": "ID proof image is required", "success": False}, status=400)
            
            try:
                staff = Staff.objects.get(id=staff_id, hotel=hotel)
                
                # Update the ID proof fields
                staff.id_proof_type = id_proof_type
                staff.id_proof_number = id_proof_number
                staff.id_proof_image = id_proof_image
                staff.save()
                
                # Build full URL
                request_host = request.get_host()
                request_scheme = request.scheme
                id_proof_image_url = f"{request_scheme}://{request_host}{staff.id_proof_image.url}"
                
                # Get display label for ID type
                id_proof_type_display = dict(staff._meta.get_field('id_proof_type').choices).get(id_proof_type, 'ID Proof')
                
                return JsonResponse({
                    "success": True,
                    "message": "ID Proof uploaded successfully",
                    "id_proof_image_url": id_proof_image_url,
                    "id_proof_type": staff.id_proof_type,
                    "id_proof_type_label": id_proof_type_display,
                    "id_proof_number": staff.id_proof_number
                })
                
            except Staff.DoesNotExist:
                return JsonResponse({"error": "Staff not found", "success": False}, status=404)
                
    except Hotel.DoesNotExist:
        return JsonResponse({"error": "Hotel not found", "success": False}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e), "success": False}, status=500)
@require_POST
def delete_staff(request):
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
            staff_id = data.get("staff_id")
        else:
            staff_id = request.POST.get("staff_id")

        print("DEBUG staff_id:", staff_id)

        if not staff_id:
            return JsonResponse({"error": "Staff ID required"}, status=400)

        
        tenant = connection.tenant
        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=tenant.schema_name)

        staff_obj = Staff.objects.filter(id=staff_id, hotel=hotel).first()

        if not staff_obj:
            return JsonResponse({"error": "Staff not found"}, status=404)

       
        user = staff_obj.user
        staff_obj.delete()
        if user:
            user.delete()

        return JsonResponse({
            "success": True,
            "message": "Employee deleted successfully"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def update_staff(request):
    try:
        staff_id = request.POST.get("staff_id")

        if not staff_id:
            return JsonResponse({"error": "Staff ID required"}, status=400)

        
        tenant = connection.tenant
        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=tenant.schema_name)

        staff_obj = Staff.objects.filter(id=staff_id, hotel=hotel).first()

        if not staff_obj:
            return JsonResponse({"error": "Staff not found"}, status=404)

       
        staff_obj.name   = request.POST.get("name", staff_obj.name)
        staff_obj.phone  = request.POST.get("phone", staff_obj.phone)
        staff_obj.salary = request.POST.get("salary", staff_obj.salary)
        staff_obj.role   = request.POST.get("role", getattr(staff_obj, "role", "Staff"))

        dept_id = request.POST.get("department")
        if dept_id:
            try:
                staff_obj.department_id = int(dept_id)
            except (ValueError, TypeError):
                pass

        if request.FILES.get("photo"):
            staff_obj.photo = request.FILES["photo"]

        staff_obj.save()

       
        new_email = request.POST.get("email", "").strip()
        if new_email and staff_obj.user:
            staff_obj.user.email    = new_email
            staff_obj.user.username = new_email
            staff_obj.user.save()

        return JsonResponse({
            "success": True,
            "message": "Updated",
            "staff": {
                "id": staff_obj.id,
                "name": staff_obj.name,
                "email": staff_obj.user.email if staff_obj.user else "",
                "phone": staff_obj.phone,
                "department": staff_obj.department.name if staff_obj.department else None,
                "salary": str(staff_obj.salary),
                "role": getattr(staff_obj, "role", "Staff"),
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


def staff_login(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        if not email or not password:
            return render(request, "staff_login.html", {
                "error": "Enter email and password"
            })

        current_tenant = connection.tenant

        with schema_context('public'):
            try:
                hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)
            except Hotel.DoesNotExist:
                return render(request, "staff_login.html", {
                    "error": "Hotel not found"
                })

        unique_username = f"{email}_{hotel.id}"

        with schema_context(current_tenant.schema_name):
            user = authenticate(request, username=unique_username, password=password)
            if user is None:
                user = authenticate(request, username=email, password=password)

        if user is None:
            return render(request, "staff_login.html", {
                "error": "Invalid credentials"
            })

        if not user.is_active:
            return render(request, "staff_login.html", {
                "error": "Account disabled"
            })

        with schema_context(current_tenant.schema_name):
            staff = Staff.objects.select_related("department", "hotel")\
                .filter(user=user, hotel=user.hotel)\
                .first()

        if not staff:
            return render(request, "staff_login.html", {
                "error": "Access denied for this hotel"
            })

        if not staff.is_active:
            return render(request, "staff_login.html", {
                "error": "Staff account inactive"
            })

        if not user.is_active_staff:
            return render(request, "staff_login.html", {
                "error": "User access disabled"
            })

        login(request, user)

        request.session["staff_id"] = staff.id
        request.session["hotel_id"] = staff.hotel.id
        request.session["department"] = staff.department.name if staff.department else ""

        dept = (staff.department.name.lower() if staff.department else "")

        redirect_map = {
            "housekeeping": "housekeeping_dashboard",
            "hr": "hr_dashboard",
            "front desk": "frontoffice_dashboard",
            "front office": "frontoffice_dashboard",
            "accountant": "accountant_dashboard",
            "restaurant": "restaurant_dashboard",
        }

        return redirect(redirect_map.get(dept, "restaurant_dashboard"))

    return render(request, "staff_login.html")
from django.contrib.auth import logout
@never_cache
def logout_view(request):
    logout(request)             
    request.session.flush()     
    response = redirect('hotel_login')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response
@never_cache
def staff_logout(request):
    logout(request)
    request.session.flush()

    response = redirect('staff_login')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    return response
@never_cache
@login_required
def hotel_setup(request):
    from pms.models import Room, RoomUnit, RoomImage
    from django.utils import timezone
    from accounts.models import HotelModule

    current_tenant = connection.tenant
    _sync_statuses()
    with schema_context('public'):
        hotel = get_object_or_404(
            Hotel.objects.select_related('subscription_plan'),
            schema_name=current_tenant.schema_name
        )

        if hotel.is_setup_complete and request.GET.get("edit") != "true":
            return redirect('dashboard')

        if request.GET.get('skip') == 'true':
            hotel.is_setup_complete = True
            hotel.save()
            return redirect('dashboard')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'hotel_details':
            with schema_context('public'):
                hotel.hotel_name    = request.POST.get('hotel_name',    hotel.hotel_name)
                hotel.owner_name    = request.POST.get('owner_name',    hotel.owner_name)
                hotel.address       = request.POST.get('address',       hotel.address)
                hotel.city          = request.POST.get('city',          hotel.city)
                hotel.state         = request.POST.get('state',         getattr(hotel, 'state', ''))
                hotel.phone         = request.POST.get('phone',         getattr(hotel, 'phone', ''))
                hotel.description   = request.POST.get('description',   hotel.description)
                hotel.property_type = request.POST.get('property_type', hotel.property_type)

                if request.FILES.get('logo'):
                    hotel.logo = request.FILES['logo']
                if request.FILES.get('image'):
                    hotel.image = request.FILES['image']

                hotel.save()
            return JsonResponse({'success': True})

        elif form_type == 'room_details':
            try:
                with transaction.atomic():
                    room = Room.objects.create(
                        room_type=request.POST.get('room_type'),
                        base_price=request.POST.get('base_price') or 0,
                        max_adults=request.POST.get('max_adults') or 2,
                        max_children=request.POST.get('max_children') or 0,
                        description=request.POST.get('description') or '',
                        extra_adult_price=request.POST.get('extra_adult_price') or 0,
                        extra_child_price=request.POST.get('extra_child_price') or 0,
                    )

                    amenity_ids = request.POST.getlist('amenities')
                    if amenity_ids:
                        room.amenities.set(amenity_ids)

                    total_units = int(request.POST.get('total_units') or 1)

                    prefix_map = {
                        'Single': 'S',
                        'Double': 'D',
                        'Deluxe': 'DL',
                        'Suite':  'SU',
                    }
                    prefix = prefix_map.get(room.room_type, 'R')

                    existing_numbers = set(
                        RoomUnit.objects.values_list('room_number', flat=True)
                    )

                    units, counter = [], 1
                    while len(units) < total_units:
                        number = f'{prefix}{counter}'
                        if number not in existing_numbers:
                            units.append(RoomUnit(room=room, room_number=number))
                        counter += 1

                    RoomUnit.objects.bulk_create(units)

                    for i, img in enumerate(request.FILES.getlist('images')):
                        RoomImage.objects.create(room=room, image=img, is_primary=(i == 0))

                return JsonResponse({'success': True, 'room_id': room.id})

            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)

        elif form_type == 'finish':
            with schema_context('public'):
                hotel.is_setup_complete = True
                hotel.save()
            return JsonResponse({'success': True})

        return JsonResponse({'success': False, 'error': 'Invalid form type'}, status=400)

   
    with schema_context('public'):
        hotel = Hotel.objects.select_related('subscription_plan').get(
            schema_name=current_tenant.schema_name
        )

    today = timezone.now().date()

    trial_days_remaining = 0
    if hotel.is_on_trial and hotel.trial_end:
        trial_end_date = (
            hotel.trial_end.date()
            if hasattr(hotel.trial_end, 'date')
            else hotel.trial_end
        )
        trial_days_remaining = max(0, (trial_end_date - today).days)

    subscription_plan = hotel.subscription_plan
    active_plan_name  = subscription_plan.name  if subscription_plan else None
    active_plan_price = subscription_plan.price if subscription_plan else None

    # Active modules from tenant schema
    active_modules = []
    try:
        with schema_context(current_tenant.schema_name):
            active_modules = list(
                HotelModule.objects
                .filter(hotel=hotel, is_enabled=True)
                .values_list('module__name', flat=True)
            )
    except Exception:
        pass

    if not active_modules and (hotel.is_subscribed or hotel.is_on_trial):
        try:
            if subscription_plan:
                _enable_plan_modules(hotel, subscription_plan)
            else:
                _enable_core_modules(hotel)
            with schema_context(current_tenant.schema_name):
                active_modules = list(
                    HotelModule.objects
                    .filter(hotel=hotel, is_enabled=True)
                    .values_list('module__name', flat=True)
                )
        except Exception:
            pass

    active_modules_count = len(active_modules)

  
    subscription_expiry      = hotel.subscription_expiry
    subscription_expiry_date = None
    expiry_days_remaining    = 0

    if subscription_expiry:
        subscription_expiry_date = subscription_expiry  # already a date
        expiry_days_remaining    = max(0, (subscription_expiry_date - today).days)

    subscription_status = hotel.subscription_status or ''

    show_subscription_gate = (
        not hotel.is_on_trial
        and not hotel.is_subscribed
        and subscription_status == 'expired'
    )
    show_trial_banner   = hotel.is_on_trial and not show_subscription_gate
    show_expiry_warning = (
        hotel.is_subscribed
        and not show_subscription_gate
        and not show_trial_banner
        and 0 < expiry_days_remaining <= 7
    )

    context = {
        'hotel':                  hotel,
        'show_trial_banner':      show_trial_banner,
        'trial_days_remaining':   trial_days_remaining,
        'show_subscription_gate': show_subscription_gate,
        'show_expiry_warning':    show_expiry_warning,
        'expiry_days_remaining':  expiry_days_remaining,
        'subscription_expiry':    subscription_expiry_date,
        'active_plan_name':       active_plan_name,
        'active_plan_price':      active_plan_price,
        'active_modules':         active_modules,
        'active_modules_count':   active_modules_count,
        'subscription_plan':      subscription_plan,
    }

    return render(request, 'setup.html', context)
@login_required
def hotel_subscription_summary(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    with schema_context('public'):
        hotels = Hotel.objects.select_related('subscription_plan').order_by('-created_at')
        data = [
            {
                "id":                   h.id,
                "hotel_name":           h.hotel_name,
                "email":                h.email,
                "subscription_status":  h.subscription_status,
                "subscription_plan":    h.subscription_plan.name if h.subscription_plan else None,
                "subscription_plan_id": h.subscription_plan.id   if h.subscription_plan else None,
                "subscription_expiry":  str(h.subscription_expiry) if h.subscription_expiry else None,
                "is_subscribed":        h.is_subscribed,
                "trial_eligible":       h.trial_eligible,
                "is_on_trial":          h.is_on_trial,
                "trial_is_active":      h.trial_is_active,
                "trial_has_expired":    h.trial_has_expired,
                "trial_start":          h.trial_start.strftime("%d %b %Y") if h.trial_start else None,
                "trial_end":            h.trial_end.strftime("%d %b %Y")   if h.trial_end   else None,
                "trial_days_remaining": max(0, (h.trial_end - timezone.now()).days) if h.trial_is_active else 0,
            }
            for h in hotels
        ]
 
    return JsonResponse({"hotels": data})
 
@require_POST
@login_required
def grant_trial(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    data = json.loads(request.body) if request.body else {}

    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=hotel_id)

        if not hotel.trial_eligible:
            return JsonResponse({"error": "Not eligible for trial."}, status=400)

        if hotel.subscription_status in ('active', 'trial'):
            return JsonResponse({"error": "Already has active subscription or trial."}, status=400)

        days = int(data.get("days", hotel.trial_days))

        
        plan_id = data.get("plan_id")
        plan = None
        if plan_id:
            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            hotel.subscription_plan = plan  # assign the plan to hotel
            hotel.save(update_fields=['subscription_plan'])

        try:
            hotel.start_trial(granted_by=request.user.username, days=days)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        
        if plan:
            _enable_plan_modules(hotel, plan)
        else:
            _enable_core_modules(hotel)

    try:
        send_mail(
            subject="Your Free Trial Has Started",
            message=(
                f"Hello {hotel.hotel_name},\n\n"
                f"Your {days}-day free trial has been activated.\n"
                f"Plan: {plan.name if plan else 'Core modules only'}\n"
                f"Trial ends: {hotel.trial_end.strftime('%d %b %Y')}\n\n"
                "Regards,\nAdmin Team"
            ),
            from_email=None,
            recipient_list=[hotel.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning("Trial-grant email failed: %s", exc)

    return JsonResponse({
        "success":   True,
        "hotel":     hotel.hotel_name,
        "trial_end": hotel.trial_end.strftime("%d %b %Y"),
        "days":      days,
        "plan":      plan.name if plan else "Core only",
    })
 
@require_POST
@login_required
def revoke_trial_eligibility(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    data = json.loads(request.body) if request.body else {}
 
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=hotel_id)
        hotel.trial_eligible = False
        ended_early = False
 
        if hotel.is_on_trial:
            hotel.end_trial(reason="revoked_by_admin")
            _disable_non_core_modules(hotel)
            ended_early = True
 
        hotel.save(update_fields=['trial_eligible'])
 
    try:
        send_mail(
            subject="Trial Access Revoked",
            message=(
                f"Hello {hotel.hotel_name},\n\n"
                "Your trial eligibility has been revoked.\n"
                + (f"Reason: {data.get('reason')}\n" if data.get('reason') else "")
                + "\nRegards,\nAdmin Team"
            ),
            from_email=None,
            recipient_list=[hotel.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning("Revoke-trial email failed: %s", exc)
 
    return JsonResponse({"success": True, "hotel": hotel.hotel_name, "ended_early": ended_early})
 
 
@require_POST
@login_required
def restore_trial_eligibility(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=hotel_id)
        hotel.trial_eligible = True
        hotel.save(update_fields=['trial_eligible'])
 
    return JsonResponse({"success": True, "hotel": hotel.hotel_name})
 
 
@require_POST
@login_required
def end_trial_now(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=hotel_id)
 
        if not hotel.is_on_trial:
            return JsonResponse({"error": "Hotel is not currently on trial."}, status=400)
 
        hotel.end_trial(reason="ended_by_admin")
        _disable_non_core_modules(hotel)
 
    return JsonResponse({"success": True, "hotel": hotel.hotel_name})
 
from datetime import date 
@require_POST
@login_required
def set_subscription_status(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    data   = json.loads(request.body)
    status = data.get("status", "").strip()
    valid  = {s[0] for s in Hotel.SUBSCRIPTION_STATUS}
 
    if status not in valid:
        return JsonResponse(
            {"error": f"Invalid status. Choose from: {', '.join(sorted(valid))}"},
            status=400,
        )
 
    
    expiry_date     = None
    expiry_date_str = data.get("expiry_date", "").strip()
 
    if expiry_date_str:
        try:
            expiry_date = date.fromisoformat(expiry_date_str)  
        except ValueError:
            return JsonResponse(
                {"error": "expiry_date must be in YYYY-MM-DD format."},
                status=400,
            )
 
        if expiry_date < timezone.now().date():
            return JsonResponse(
                {"error": "expiry_date cannot be in the past."},
                status=400,
            )
 
   
    if status == "active" and not expiry_date:
        return JsonResponse(
            {"error": "expiry_date is required when setting status to 'active'."},
            status=400,
        )
 
    with schema_context("public"):
        hotel = get_object_or_404(Hotel, id=hotel_id)
 
        hotel.subscription_status = status
        hotel.is_subscribed       = status in ("active", "trial")
 
       
        if expiry_date and status in ("active", "trial"):
            hotel.subscription_expiry = expiry_date
 
       
        if status == "active" and hotel.is_on_trial:
            hotel.is_on_trial = False
 
        
        if status in ("suspended", "inactive", "expired"):
            _disable_non_core_modules(hotel)
 
        hotel.save()
 
    return JsonResponse({
        "success":             True,
        "hotel":               hotel.hotel_name,
        "status":              hotel.subscription_status,
        "is_subscribed":       hotel.is_subscribed,
        "subscription_expiry": str(hotel.subscription_expiry) if hotel.subscription_expiry else None,
    })
 
 
@require_POST
@login_required
def hotel_start_trial(request):
    current_tenant = connection.tenant
 
    with schema_context('public'):
        hotel = get_object_or_404(Hotel, schema_name=current_tenant.schema_name)
 
        if not hotel.trial_eligible:
            return JsonResponse({"error": "Your account is not eligible for a trial."}, status=400)
 
        if hotel.subscription_status in ('active', 'trial'):
            return JsonResponse({"error": "You already have an active subscription or trial."}, status=400)
 
        try:
            hotel.start_trial(granted_by="self_service")
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
 
        _enable_core_modules(hotel)
 
    return JsonResponse({
        "success":   True,
        "trial_end": hotel.trial_end.strftime("%d %b %Y"),
        "days":      hotel.trial_days,
    })
@require_POST
@login_required
def set_hotel_trial_days(request, hotel_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    data = json.loads(request.body)
    days = data.get("trial_days")

    if not days or int(days) < 1:
        return JsonResponse({"error": "trial_days must be at least 1"}, status=400)

    with schema_context('public'):
        hotel = get_object_or_404(Hotel, id=hotel_id)
        hotel.trial_days = int(days)
        hotel.save(update_fields=['trial_days'])

    return JsonResponse({
        "success":    True,
        "hotel":      hotel.hotel_name,
        "trial_days": hotel.trial_days,
    }) 
require_POST
@login_required
def set_subscription_expiry(request, hotel_id):
   
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
 
    data            = json.loads(request.body)
    expiry_date_str = data.get("expiry_date", "").strip()
 
    if not expiry_date_str:
        return JsonResponse({"error": "expiry_date is required."}, status=400)
 
    try:
        expiry_date = date.fromisoformat(expiry_date_str)
    except ValueError:
        return JsonResponse(
            {"error": "expiry_date must be in YYYY-MM-DD format."},
            status=400,
        )
 
    if expiry_date < timezone.now().date():
        return JsonResponse(
            {"error": "expiry_date cannot be in the past."},
            status=400,
        )
 
    with schema_context("public"):
        hotel = get_object_or_404(Hotel, id=hotel_id)
 
       
        if hotel.subscription_status not in ("active", "trial"):
            return JsonResponse(
                {
                    "error": (
                        f"Cannot set expiry for a hotel with status "
                        f"'{hotel.subscription_status}'. "
                        "Activate the subscription first."
                    )
                },
                status=400,
            )
 
        old_expiry = hotel.subscription_expiry
        hotel.subscription_expiry = expiry_date
        hotel.save(update_fields=["subscription_expiry"])
 
    logger.info(
        "Superadmin %s updated expiry for hotel %s: %s → %s",
        request.user.username,
        hotel.hotel_name,
        old_expiry,
        expiry_date,
    )
 
    return JsonResponse({
        "success":             True,
        "hotel":               hotel.hotel_name,
        "old_expiry":          str(old_expiry) if old_expiry else None,
        "subscription_expiry": str(hotel.subscription_expiry),
    })
 