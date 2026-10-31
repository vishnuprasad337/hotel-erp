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
from .models import Hotel, Department, Permission, RolePermission, Amenity, HotelModule,RejectedHotel
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
        all_hotels  = list(Hotel.objects.all().order_by("-id"))
        approved    = [h for h in all_hotels if h.is_approved]
        pending     = [h for h in all_hotels if not h.is_approved]
        amenities   = list(Amenity.objects.all())
        plans       = list(SubscriptionPlan.objects.prefetch_related('modules').all())
        rejected    = list(RejectedHotel.objects.all().order_by("-rejected_at"))
 
    return render(request, "admin/dashboard.html", {
        "hotels":             all_hotels,
        "approved_hotels":    approved,
        "pending_hotel_list": pending,
        "total_hotels":       len(all_hotels),
        "active_hotels":      len(approved),
        "pending_hotels":     len(pending),
        "amenities":          amenities,
        "plans":              plans,
        "rejected_hotels":    rejected,
        "rejected_count":     len(rejected),
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

        # Find the tenant's domain so we can send the access link
        client = Client.objects.filter(schema_name=hotel.schema_name).first()
        domain_obj = (
            Domain.objects.filter(tenant=client, is_primary=True).first()
            if client else None
        )
        site_url = f"http://{domain_obj.domain}{settings.PORT}" if domain_obj else None

    try:
        send_mail(
            subject="Hotel Approved  ",
            message=f"""
Hello {hotel.hotel_name},

Your hotel registration has been APPROVED.

You can now login and use the system here:
{site_url or "Please contact support for your access link."}

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

    if request.method == "POST":
        data = json.loads(request.body) if request.content_type == "application/json" else {}
        reason = data.get("reason", "").strip() or "Not meeting requirements"
    else:
        reason = request.GET.get("reason", "Not meeting requirements")

    with schema_context('public'):
        RejectedHotel.objects.create(
            hotel_name       = hotel.hotel_name,
            email            = hotel.email,
            owner_name       = hotel.owner_name,
            address          = hotel.address,
            city             = hotel.city,
            property_type    = hotel.property_type,
            description      = hotel.description or "",
            schema_name      = hotel.schema_name,
            image            = hotel.image,
            rejection_reason = reason,
            rejected_by      = request.user.username,
        )

    try:
        send_mail(
            subject="Hotel Registration Rejected ❌",
            message=f"""Hello {hotel.hotel_name},

Your hotel registration has been rejected.

Reason: {reason}

You may update your details and register again.

Regards,
Admin Team""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[hotel.email],
            fail_silently=False
        )
        messages.success(request, f"Rejection email sent to '{hotel.hotel_name}'.")
    except Exception as e:
        messages.warning(request, f"Hotel rejected, but email failed: {e}")

    with schema_context('public'):
        from django_tenants.utils import get_tenant_model
        tenant_table = get_tenant_model()._meta.db_table

        with connection.cursor() as cursor:
            
            cursor.execute('DROP SCHEMA IF EXISTS "{}" CASCADE'.format(hotel.schema_name))

           
            cursor.execute(
                f'SELECT id FROM public.{tenant_table} WHERE schema_name = %s',
                [hotel.schema_name]
            )
            row = cursor.fetchone()

            if row:
                tenant_id = row[0]

                
                cursor.execute(
                    'DELETE FROM public.customers_domain WHERE tenant_id = %s',
                    [tenant_id]
                )

                
                cursor.execute(
                    f'DELETE FROM public.{tenant_table} WHERE id = %s',
                    [tenant_id]
                )

            
            cursor.execute(
                'DELETE FROM public.customers_client WHERE schema_name = %s',
                [hotel.schema_name]
            )

          
            cursor.execute(
                'DELETE FROM public.accounts_user WHERE hotel_id = %s',
                [hotel.id]
            )

            
            cursor.execute(
                'DELETE FROM public.accounts_hotel WHERE id = %s',
                [hotel.id]
            )

    return JsonResponse({"success": True})
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

@login_required
def get_rejected_hotels(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    with schema_context('public'):
        rejected = RejectedHotel.objects.all().order_by('-rejected_at')
        data = [
            {
                "id":               r.id,
                "hotel_name":       r.hotel_name,
                "email":            r.email,
                "owner_name":       r.owner_name,
                "address":          r.address,
                "city":             r.city,
                "property_type":    r.property_type,
                "description":      r.description,
                "rejection_reason": r.rejection_reason,
                "rejected_by":      r.rejected_by,
                "rejected_at":      r.rejected_at.strftime("%d %b %Y %H:%M"),
                "image":            r.image.url if r.image else None,
            }
            for r in rejected
        ]
    return JsonResponse({"rejected_hotels": data, "total": len(data)})
##----------------------Hotel Authentication----------------------

import random
from datetime import timedelta
from django.contrib.auth.hashers import make_password
from .models import PendingHotelRegistration

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def _generate_otp():
    return f"{random.randint(0, 999999):06d}"


def _send_otp_email(pending):
    try:
        send_mail(
            subject="Your OTP Code - Hotel Registration",
            message=(
                f"Hello {pending.hotel_name},\n\n"
                f"Your OTP code is: {pending.otp_code}\n"
                f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
                "If you did not request this, please ignore this email.\n\n"
                "Regards,\nAdmin Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending.email],
            fail_silently=False,   # was True — this is what's hiding the real error
        )
    except Exception as e:
        import traceback
        print("OTP EMAIL SEND FAILED:", repr(e))
        traceback.print_exc()
        logger.warning("OTP email failed for %s: %s", pending.email, e)
def hotel_register(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == "POST":
        form = HotelForm(request.POST, request.FILES)

        if form.is_valid():
            email = form.cleaned_data["email"]

            with schema_context('public'):
                if Hotel.objects.filter(email__iexact=email).exists():
                    error_msg = "A hotel with this email is already registered."
                    if is_ajax:
                        return JsonResponse({"success": False, "error": error_msg, "form_errors": {"email": error_msg}}, status=400)
                    form.add_error("email", error_msg)
                    return render(request, "register.html", {"tenant_form": form})

                # Clear out any earlier unfinished attempt for this email
                PendingHotelRegistration.objects.filter(email__iexact=email).delete()

                pending = PendingHotelRegistration(
                    hotel_name    = form.cleaned_data["hotel_name"],
                    email         = email,
                    owner_name    = form.cleaned_data["owner_name"],
                    address       = form.cleaned_data["address"],
                    city          = form.cleaned_data["city"],
                    property_type = form.cleaned_data["property_type"],
                    description   = form.cleaned_data.get("description") or "",
                    amenities     = form.cleaned_data.get("amenities") or "",
                    password_hash = make_password(form.cleaned_data["password"]),
                    otp_code      = _generate_otp(),
                    otp_created_at= timezone.now(),
                )

                if form.cleaned_data.get("image"):
                    pending.image = form.cleaned_data["image"]

                pending.auto_approve = request.POST.get('auto_approve') == '1'
                pending.grant_trial  = request.POST.get('grant_trial') == '1'
                pending.trial_days   = int(request.POST.get('trial_days') or 14)
                plan_id_raw          = request.POST.get('plan_id', '').strip()
                pending.plan_id      = int(plan_id_raw) if plan_id_raw.isdigit() else None

                pending.save()

            _send_otp_email(pending)

            if is_ajax:
                return JsonResponse({
                    "success":     True,
                    "require_otp": True,
                    "email":       email,
                    "message":     "OTP sent to your email. Please verify to complete registration.",
                })
            return render(request, "register.html", {
                "tenant_form": HotelForm(),
                "otp_stage": True,
                "otp_email": email,
            })

        else:
            if is_ajax:
                errors = {field: errs.as_text() for field, errs in form.errors.items()}
                readable = "; ".join(f"{field}: {msg.replace('* ', '')}" for field, msg in errors.items())
                return JsonResponse({"success": False, "error": readable, "form_errors": errors}, status=400)
            return render(request, "register.html", {"tenant_form": form})

    return render(request, "register.html", {"tenant_form": HotelForm()})

@require_POST
def verify_hotel_otp(request):
    if request.content_type == "application/json":
        data = json.loads(request.body)
    else:
        data = request.POST

    email    = (data.get("email") or "").strip()
    otp_code = (data.get("otp") or "").strip()

    if not email or not otp_code:
        return JsonResponse({"success": False, "error": "Email and OTP are required."}, status=400)

    with schema_context('public'):
        pending = PendingHotelRegistration.objects.filter(email__iexact=email).first()

        if not pending:
            return JsonResponse({"success": False, "error": "No pending registration found. Please register again."}, status=400)

        if timezone.now() > pending.otp_created_at + timedelta(minutes=OTP_EXPIRY_MINUTES):
            pending.delete()
            return JsonResponse({"success": False, "error": "OTP has expired. Please register again."}, status=400)

        if pending.otp_attempts >= MAX_OTP_ATTEMPTS:
            pending.delete()
            return JsonResponse({"success": False, "error": "Too many incorrect attempts. Please register again."}, status=400)

        if pending.otp_code != otp_code:
            pending.otp_attempts += 1
            pending.save(update_fields=['otp_attempts'])
            remaining = MAX_OTP_ATTEMPTS - pending.otp_attempts
            return JsonResponse({"success": False, "error": f"Incorrect OTP. {remaining} attempt(s) left."}, status=400)

    # OTP verified — now actually create the hotel/client/user
    try:
        with transaction.atomic():
            with schema_context('public'):
                hotel = Hotel(
                    hotel_name    = pending.hotel_name,
                    email         = pending.email,
                    owner_name    = pending.owner_name,
                    address       = pending.address,
                    city          = pending.city,
                    property_type = pending.property_type,
                    description   = pending.description,
                    amenities     = pending.amenities,
                )
                if pending.image:
                    hotel.image = pending.image

                base_schema = slugify(hotel.hotel_name)
                schema_name = base_schema
                counter = 1
                while Client.objects.filter(schema_name=schema_name).exists():
                    schema_name = f"{base_schema}{counter}"
                    counter += 1

                client = Client.objects.create(schema_name=schema_name, name=hotel.hotel_name)
                hotel.schema_name = schema_name

                if pending.auto_approve:
                    hotel.is_approved = True

                hotel.save()

                domain = Domain.objects.create(
                    tenant=client,
                    domain=f"{schema_name}.{settings.BASE_URL}",
                    is_primary=True
                )

                plan = None
                if pending.plan_id:
                    try:
                        plan = SubscriptionPlan.objects.get(id=pending.plan_id)
                        hotel.subscription_plan = plan
                        hotel.save(update_fields=['subscription_plan'])
                    except SubscriptionPlan.DoesNotExist:
                        pass

            with schema_context(schema_name):
                user = User.objects.create(
                    username=hotel.email,
                    email=hotel.email,
                    hotel=hotel,
                )
                user.password = pending.password_hash  # already hashed via make_password
                user.save(update_fields=['password'])

            if pending.grant_trial:
                with schema_context('public'):
                    try:
                        hotel.trial_days = pending.trial_days
                        hotel.save(update_fields=['trial_days'])
                        hotel.start_trial(granted_by="superadmin")
                        if plan:
                            _enable_plan_modules(hotel, plan)
                        else:
                            _enable_core_modules(hotel)
                    except Exception as trial_err:
                        logger.warning("Trial grant failed during registration: %s", trial_err)

        with schema_context('public'):
            pending.delete()

        try:
            if pending.auto_approve:
                subject = "Hotel Registration Approved ✅"
                message = f"""Hello {hotel.hotel_name},

Your hotel has been registered and approved by the admin.

Login URL: http://{domain.domain}{settings.PORT}

Regards,
Admin Team"""
            else:
                subject = "Registration Received - Pending Approval"
                message = f"""Hello {hotel.hotel_name},

Thank you for registering! Your application is pending admin approval.

Regards,
Admin Team"""

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[hotel.email],
                fail_silently=True
            )
        except Exception as e:
            logger.warning("Registration email error: %s", e)

        return JsonResponse({
            "success":      True,
            "hotel_name":   hotel.hotel_name,
            "schema_name":  schema_name,
            "domain":       domain.domain,
            "is_approved":  hotel.is_approved,
            "redirect_url": f"http://{domain.domain}{settings.PORT}",
        })

    except Exception as e:
        logger.error("Hotel registration finalize error: %s", e)
        import traceback; traceback.print_exc()
        return JsonResponse({"success": False, "error": "Something went wrong finishing registration."}, status=400)


@require_POST
def resend_hotel_otp(request):
    if request.content_type == "application/json":
        data = json.loads(request.body)
    else:
        data = request.POST

    email = (data.get("email") or "").strip()
    if not email:
        return JsonResponse({"success": False, "error": "Email is required."}, status=400)

    with schema_context('public'):
        pending = PendingHotelRegistration.objects.filter(email__iexact=email).first()
        if not pending:
            return JsonResponse({"success": False, "error": "No pending registration found."}, status=400)

        cooldown_end = pending.otp_created_at + timedelta(seconds=RESEND_COOLDOWN_SECONDS)
        if timezone.now() < cooldown_end:
            wait = int((cooldown_end - timezone.now()).total_seconds())
            return JsonResponse({"success": False, "error": f"Please wait {wait}s before resending."}, status=429)

        pending.otp_code = _generate_otp()
        pending.otp_created_at = timezone.now()
        pending.otp_attempts = 0
        pending.save(update_fields=['otp_code', 'otp_created_at', 'otp_attempts'])

    _send_otp_email(pending)
    return JsonResponse({"success": True, "message": "OTP resent."})
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
        is_core     = bool(data.get("is_core", False))   

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
from django.views.decorators.http import require_GET
from django_tenants.utils import schema_context
from django.http import JsonResponse
from .models import SubscriptionPlan
from django.db.models import Q

@require_GET
def get_plans(request):
    try:
        with schema_context('public'):
            plans = SubscriptionPlan.objects.prefetch_related('modules').all()

            is_superadmin = request.user.is_authenticated and request.user.is_superuser
            hotel = None
            hotel_used_trial_plan_id = None

            if not is_superadmin:
                today = timezone.now().date()

                current_tenant = connection.tenant
                try:
                    hotel = Hotel.objects.select_related('subscription_plan').get(
                        schema_name=current_tenant.schema_name
                    )
                except Hotel.DoesNotExist:
                    hotel = None

                if hotel:
                    is_actively_subscribed = (
                        hotel.subscription_status == 'active'
                        and hotel.is_subscribed
                        and hotel.subscription_expiry
                        and hotel.subscription_expiry >= today
                    )
                    if is_actively_subscribed:
                        return JsonResponse({
                            "plans":         [],
                            "total":         0,
                            "is_superadmin": False,
                            "subscribed":    True,
                            "current_plan":  hotel.subscription_plan.name if hotel.subscription_plan else None,
                            "expiry":        str(hotel.subscription_expiry),
                            "message":       "You already have an active subscription.",
                        })

                    if hotel.is_on_trial or hotel.trial_has_expired:
                        hotel_used_trial_plan_id = (
                            hotel.subscription_plan.id
                            if hotel.subscription_plan
                            else -1
                        )

                plans = plans.filter(is_active=True).filter(
                    Q(valid_until__isnull=True) | Q(valid_until__gte=today)
                )

            data = [
                {
                    "id":                  p.id,
                    "name":                p.name,
                    "price":               str(p.price),
                    "tagline":             getattr(p, 'tagline', '') or '',
                    "is_active":           p.is_active,
                    "valid_until":         str(p.valid_until) if getattr(p, 'valid_until', None) else None,
                    "trial_days":          getattr(p, 'trial_days', 14) or 14,
                    "module_ids":          list(p.modules.values_list("id", flat=True)),
                    "module_names":        list(p.modules.values_list("name", flat=True)),
                    "user_has_used_trial": (hotel_used_trial_plan_id == p.id) if hotel else False,
                }
                for p in plans
            ]

        return JsonResponse({
            "plans":         data,
            "total":         len(data),
            "is_superadmin": is_superadmin,
            "subscribed":    False,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
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

        print(f"\n{'='*60}")
        print(f"SAVE HOTEL MODULES — hotel_id: {hotel_id}")
        print(f"Requested module_ids: {module_ids}")

        with schema_context('public'):
            hotel = get_object_or_404(Hotel, id=hotel_id)
            target_schema = hotel.schema_name

            core_ids = set(
                Amenity.objects.filter(is_core=True).values_list('id', flat=True)
            )
            print(f"Core IDs: {core_ids}")

            plan_ids = set()
            if hotel.subscription_plan:
                plan_ids = set(
                    hotel.subscription_plan.modules.values_list('id', flat=True)
                )
            print(f"Plan IDs: {plan_ids}")

            if request.user.is_superuser:
                valid_ids = [int(mid) for mid in module_ids]
                print(f"Superuser — all requested IDs accepted: {valid_ids}")
            else:
                allowed_ids = core_ids | plan_ids
                valid_ids = [int(mid) for mid in module_ids if int(mid) in allowed_ids]
                print(f"Non-superuser — filtered valid_ids: {valid_ids}")

            amenities = list(Amenity.objects.filter(id__in=valid_ids))
            print(f"Amenities to save: {[a.name for a in amenities]}")

        with schema_context(target_schema):
            # Snapshot before
            before = list(
                HotelModule.objects.filter(hotel=hotel)
                .values_list('module__name', 'is_enabled')
            )
            print(f"BEFORE SAVE — existing HotelModules: {before}")

            # Delete all non-core modules first
            deleted_count, _ = HotelModule.objects.filter(
                hotel=hotel, module__is_core=False
            ).delete()
            print(f"Deleted {deleted_count} non-core HotelModule records")

            # Re-create selected non-core modules with is_enabled=True
            for amenity in amenities:
                if not amenity.is_core:
                    obj, created = HotelModule.objects.get_or_create(
                        hotel=hotel,
                        module=amenity,
                        defaults={'is_enabled': True}   # ← FIX: was missing
                    )
                    if not created and not obj.is_enabled:
                        # Edge case: record existed but was disabled — force enable
                        obj.is_enabled = True
                        obj.save(update_fields=['is_enabled'])
                        print(f"  Re-enabled existing module: {amenity.name}")
                    else:
                        print(f"  {'Created' if created else 'Already exists'}: {amenity.name} (is_enabled=True)")

            # Ensure ALL core modules exist and are enabled (never remove them)
            for cid in core_ids:
                obj, created = HotelModule.objects.get_or_create(
                    hotel=hotel,
                    module_id=cid,
                    defaults={'is_enabled': True}
                )
                if not created and not obj.is_enabled:
                    obj.is_enabled = True
                    obj.save(update_fields=['is_enabled'])
                    print(f"  Re-enabled core module id={cid}")
                else:
                    print(f"  Core module id={cid}: {'created' if created else 'already exists'}")

            # Snapshot after
            after = list(
                HotelModule.objects.filter(hotel=hotel)
                .values_list('module__name', 'is_enabled')
            )
            print(f"AFTER SAVE — HotelModules: {after}")

        # Mark hotel as manually configured — dashboard sync will respect this
        with schema_context('public'):
            hotel.modules_manually_configured = True
            hotel.save(update_fields=['modules_manually_configured'])
            print(f"Hotel '{hotel.hotel_name}' marked as modules_manually_configured=True")

        print(f"{'='*60}\n")
        return JsonResponse({"success": True})

    except Exception as e:
        import traceback
        traceback.print_exc()
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
from collections import defaultdict
from datetime import timedelta


from datetime import datetime, timedelta
from django.http import JsonResponse


def _serialize_recent_bookings(bookings_qs):
    """Shared serializer used by both the full-page render and the AJAX
    date-range response, so the two never drift out of sync."""
    recent_bookings = []
    for b in bookings_qs:
        guest_name = "—"
        if b.guest:
            guest_name = (
                getattr(b.guest, 'full_name', None)
                or getattr(b.guest, 'name', None)
                or f"{getattr(b.guest, 'first_name', '')} {getattr(b.guest, 'last_name', '')}".strip()
                or str(b.guest)
            )

        room_label = "—"
        if b.room:
            room_label = (
                b.room.custom_room_type
                if b.room.room_type == 'Custom' and b.room.custom_room_type
                else b.room.room_type
            )
        if b.room_unit:
            room_label = f"{room_label} ({b.room_unit.room_number})"

        recent_bookings.append({
            "id": b.id,
            "guest_name": guest_name,
            "room_label": room_label,
            "check_in": str(b.check_in),
            "status": b.status,
            "total_amount": str(b.total_amount),
        })
    return recent_bookings


def _build_range_data(start_date, end_date):
    """Everything that depends on the selected date range: the hero label,
    the check-in/check-out trend chart, the bookings count + growth badge,
    and the recent-bookings table for that window."""
    weekly_labels = []
    weekly_checkins = []
    weekly_checkouts = []

    num_days = (end_date - start_date).days + 1
    for i in range(num_days):
        day = start_date + timedelta(days=i)
        weekly_labels.append(day.strftime("%a %d"))
        weekly_checkins.append(Booking.objects.filter(check_in=day).count())
        weekly_checkouts.append(Booking.objects.filter(check_out=day).count())

    total_bookings_in_range = Booking.objects.filter(
        check_in__gte=start_date, check_in__lte=end_date
    ).count()

    # growth = this range's check-ins+check-outs vs. an equally long
    # window immediately before it
    prev_start = start_date - timedelta(days=num_days)
    prev_end = start_date - timedelta(days=1)
    current_activity = sum(weekly_checkins) + sum(weekly_checkouts)
    previous_activity = (
        Booking.objects.filter(check_in__gte=prev_start, check_in__lte=prev_end).count()
        + Booking.objects.filter(check_out__gte=prev_start, check_out__lte=prev_end).count()
    )
    if previous_activity > 0:
        bookings_growth_pct = round(((current_activity - previous_activity) / previous_activity) * 100, 1)
    else:
        bookings_growth_pct = 100.0 if current_activity > 0 else 0.0

    recent_bookings_qs = (
        Booking.objects.select_related('guest', 'room', 'room_unit')
        .filter(check_in__gte=start_date, check_in__lte=end_date)
        .order_by('-id')[:5]
    )

    date_range_display = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"

    return {
        "weekly_labels": weekly_labels,
        "weekly_checkins": weekly_checkins,
        "weekly_checkouts": weekly_checkouts,
        "total_bookings": total_bookings_in_range,
        "bookings_growth_pct": bookings_growth_pct,
        "recent_bookings": _serialize_recent_bookings(recent_bookings_qs),
        "date_range_display": date_range_display,
    }


@never_cache
@login_required
def dashboard(request):
    from pms.models import Room, RoomUnit, RoomImage, SeasonalRate
    from inventory.models import Vendor, ItemCategory

    current_tenant = connection.tenant

    today = timezone.now().date()

    # ── Parse the requested range (defaults to the last 7 days, same as before) ──
    start_param = request.GET.get('start')
    end_param = request.GET.get('end')
    try:
        week_start = datetime.strptime(start_param, "%Y-%m-%d").date() if start_param else today - timedelta(days=6)
        week_end = datetime.strptime(end_param, "%Y-%m-%d").date() if end_param else today
    except ValueError:
        week_start, week_end = today - timedelta(days=6), today
    if week_end < week_start:
        week_start, week_end = week_end, week_start

    # ── AJAX branch: the hero date-range picker calls this exact same URL
    # with ?ajax=1&start=...&end=... and only wants the range-dependent
    # data back as JSON — skip the module sync + full render below. ──
    is_ajax = request.GET.get('ajax') == '1' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return JsonResponse(_build_range_data(week_start, week_end))

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
    print(f"modules_manually_configured: {getattr(hotel, 'modules_manually_configured', False)}")

    if hotel.subscription_plan:
        with schema_context('public'):
            plan_module_names = list(
                hotel.subscription_plan.modules.values_list('name', flat=True)
            )
        print(f"PLAN MODULES ({len(plan_module_names)}): {plan_module_names}")
    else:
        print("PLAN MODULES: No plan assigned")

    before_modules = list(
        HotelModule.objects.filter(hotel=hotel)
        .select_related('module')
        .values_list('module__name', flat=True)
    )
    print(f"BEFORE SYNC — HotelModule records ({len(before_modules)}): {before_modules}")

    manually_configured = getattr(hotel, 'modules_manually_configured', False)

    if manually_configured:
        print(">>> modules_manually_configured=True — preserving manual assignments")
        _enable_core_modules(hotel)
        print(">>> Core modules ensured, manual module choices preserved")
    else:
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

    after_modules = list(
        HotelModule.objects.filter(hotel=hotel, is_enabled=True)
        .select_related('module')
        .values_list('module__name', flat=True)
    )
    print(f"AFTER SYNC — HotelModule records ({len(after_modules)}): {after_modules}")

    rooms = Room.objects.filter(is_active=True)
    seasonal_rates = list(SeasonalRate.objects.filter(room__in=rooms).values(
        'id', 'room_id', 'start_date', 'end_date', 'price', 'reason'
    ))

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
    active_module_names = list(active_module_names)

    # ── Core room stats (current live state, not date-range dependent) ──
    all_units = RoomUnit.objects.select_related('room')
    total_rooms = all_units.count()
    available_rooms = all_units.filter(status="Available").count()
    occupied_rooms = all_units.filter(status="Occupied").count()
    total_staff = Staff.objects.count()

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

    # ── Occupancy / availability rates ──
    occupancy_rate = round((occupied_rooms / total_rooms) * 100, 1) if total_rooms else 0
    availability_rate = round((available_rooms / total_rooms) * 100, 1) if total_rooms else 0

    # ── Occupancy by Room Type ──
    type_totals = defaultdict(lambda: {"total": 0, "occupied": 0})
    for unit in all_units:
        rtype = (
            unit.room.custom_room_type
            if unit.room.room_type == 'Custom' and unit.room.custom_room_type
            else unit.room.room_type
        )
        type_totals[rtype]["total"] += 1
        if unit.status == "Occupied":
            type_totals[rtype]["occupied"] += 1

    room_type_occupancy = [
        {
            "type": rtype,
            "occupied": counts["occupied"],
            "total": counts["total"],
            "pct": int((counts["occupied"] / counts["total"]) * 100) if counts["total"] else 0,
        }
        for rtype, counts in type_totals.items()
    ]

    # Chart-ready arrays for the grouped bar chart
    room_type_labels = [rt["type"] for rt in room_type_occupancy]
    room_type_occupied_data = [rt["occupied"] for rt in room_type_occupancy]
    room_type_total_data = [rt["total"] for rt in room_type_occupancy]

    # ── Live Room Status breakdown ──
    status_config = [
        ("Available", "green"),
        ("Occupied", "red"),
        ("Dirty", "orange"),
        ("Reserved", "purple"),
        ("Cleaning", "cyan"),
        ("Maintenance", "gray"),
    ]
    room_status_breakdown = [
        {"label": label, "count": all_units.filter(status=label).count(), "color": color}
        for label, color in status_config
    ]
    dirty_rooms = all_units.filter(status="Dirty").count()

    # ── Range-dependent data: trend chart, bookings count/growth, recent
    # bookings — all computed once here for the requested week_start/week_end
    # (defaults to the last 7 days) so the initial page load and the AJAX
    # picker always agree. ──
    range_data = _build_range_data(week_start, week_end)

    # ── Departments / Categories / Vendors ──
    with schema_context(current_tenant.schema_name):
        departments = list(Department.objects.all().values('id', 'name'))

        categories = list(
            ItemCategory.objects.all().values(
                'id',
                'name'
            )
        )

        vendors = list(
            Vendor.objects.all().values(
                'id',
                'name',
                'contact_person',
                'phone',
                'email',
                'address'
            )
        )

        # ── Today's Shifts (placeholder — swap for real Shift model when available) ──
        today_shifts = list(
            Staff.objects.filter(hotel=hotel, is_active=True)
            .select_related('department')
            .values('id', 'name', 'department__name')[:10]
        )

    return render(request, "hotel/property.html", {
        "hotel": hotel,
        "amenities": amenities,
        "active_module_names": active_module_names,
        "total_rooms": total_rooms,
        "available_rooms": available_rooms,
        "occupied_rooms": occupied_rooms,
        "dirty_rooms": dirty_rooms,
        "total_staff": total_staff,
        "total_bookings": range_data["total_bookings"],
        "reserved_count": reserved_count,
        "today_checkins": today_checkins,
        "today_checkouts": today_checkouts,
        "occupancy_rate": occupancy_rate,
        "availability_rate": availability_rate,
        "bookings_growth_pct": range_data["bookings_growth_pct"],
        "departments": departments,
        "departments_json": json.dumps(list(departments)),
        "categories": categories,
        "categories_json": json.dumps(categories),
        "vendors": vendors,
        "vendors_json": json.dumps(vendors),
        "rooms": rooms,
        "seasonal_rates_json": json.dumps(seasonal_rates, default=str),
        "room_type_occupancy": room_type_occupancy,
        "room_type_labels_json": json.dumps(room_type_labels),
        "room_type_occupied_json": json.dumps(room_type_occupied_data),
        "room_type_total_json": json.dumps(room_type_total_data),
        "room_status_breakdown": room_status_breakdown,
        "room_status_breakdown_json": json.dumps(room_status_breakdown),
        "today_shifts": today_shifts,
        "recent_bookings": range_data["recent_bookings"],
        "weekly_labels": json.dumps(range_data["weekly_labels"]),
        "weekly_checkins": json.dumps(range_data["weekly_checkins"]),
        "weekly_checkouts": json.dumps(range_data["weekly_checkouts"]),
        "week_start": week_start,
        "week_end": week_end,
        "date_range_display": range_data["date_range_display"],
    })
##----------------------Role & permissions----------------------
def add_department(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hotel = request.session.get("hotel_id")

        if hotel and name:
            hotel_obj = Hotel.objects.get(id=hotel)
            exists = Department.objects.filter(
                hotel=hotel_obj, name__iexact=name
            ).exists()
            if not exists:
                Department.objects.create(hotel=hotel_obj, name=name)

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
from django.db import IntegrityError, transaction

@csrf_exempt
@require_POST
def staff_register(request):
    try:
        if request.content_type and 'application/json' in request.content_type:
            data  = json.loads(request.body)
            files = {}
        else:
            data  = request.POST
            files = request.FILES

        def get_field(key, default=None):
            v = data.get(key, default or "")
            if hasattr(v, 'strip'):
                v = v.strip()
            return v if v else None

        name          = get_field("name")
        email         = get_field("email")
        password      = data.get("password", "").strip()
        phone         = get_field("phone")
        department_id = get_field("department_id") or get_field("department")
        salary        = get_field("salary") or 0
        employee_id   = get_field("employee_id")
        joining_date  = get_field("joining_date")
        role_name     = get_field("role") or "Staff"

        nickname = get_field("nickname")
        dob      = get_field("dob")
        gender   = get_field("gender")
        address  = get_field("address")

        emergency_contact_name  = get_field("emergency_contact_name")
        emergency_contact_phone = get_field("emergency_contact_phone")

        employment_type = get_field("employment_type")

        bank_account = get_field("bank_account")
        ifsc         = get_field("ifsc")
        pf_number    = get_field("pf_number")
        esi_number   = get_field("esi_number")
        notes        = get_field("notes")

        id_proof_type   = get_field("id_proof_type")
        id_proof_number = get_field("id_proof_number")
        id_proof_image  = files.get("id_proof_image") or files.get("id_proof")
        photo           = files.get("photo")

        if not all([name, email, password]):
            return JsonResponse({"error": "Name, email, and password are required"}, status=400)

        hotel_id = request.session.get("hotel_id")
        if not hotel_id:
            return JsonResponse({"error": "Session expired. Please login again."}, status=401)

        with schema_context('public'):
            try:
                hotel = Hotel.objects.get(id=hotel_id)
            except Hotel.DoesNotExist:
                return JsonResponse({"error": "Hotel not found"}, status=404)

        tenant_schema   = hotel.schema_name
        unique_username = f"{email}_{hotel.id}"

        department = None
        if department_id:
            with schema_context(tenant_schema):
                department = Department.objects.filter(id=int(department_id)).first()
                if not department:
                    return JsonResponse({"error": "Department not found"}, status=400)

        with schema_context(tenant_schema):
            with transaction.atomic():

                existing_user = (
                    User.objects
                    .select_for_update()
                    .filter(username=unique_username)
                    .first()
                )

                if existing_user:
                    has_staff = Staff.objects.filter(user=existing_user).exists()
                    print(f"DEBUG register — existing_user: {existing_user.username} | has_staff: {has_staff}")
                    if has_staff:
                        return JsonResponse(
                            {"error": "A staff member with this email already exists"},
                            status=400,
                        )
                    # Orphaned user — no staff record linked, safe to delete
                    print(f"DEBUG register — deleting orphaned user: {existing_user.username}")
                    existing_user.delete()

                try:
                    user = User.objects.create_user(
                        username=unique_username,
                        email=email,
                        password=password,
                        hotel=hotel,
                        role=None,
                    )
                except IntegrityError:
                    return JsonResponse(
                        {"error": "A staff member with this email already exists"},
                        status=400,
                    )

                try:
                    staff_kwargs = dict(
                        user=user,
                        hotel=hotel,
                        name=name,
                        phone=phone,
                        department=department,
                        salary=salary,
                        nickname=nickname,
                        dob=dob,
                        gender=gender,
                        address=address,
                        emergency_contact_name=emergency_contact_name,
                        emergency_contact_phone=emergency_contact_phone,
                        employment_type=employment_type,
                        bank_account=bank_account,
                        ifsc=ifsc,
                        pf_number=pf_number,
                        esi_number=esi_number,
                        notes=notes,
                    )

                    if employee_id:
                        duplicate = (
                            Staff.objects
                            .select_for_update()
                            .filter(hotel=hotel, employee_id=employee_id)
                            .exists()
                        )
                        if duplicate:
                            return JsonResponse(
                                {"error": f"Employee ID '{employee_id}' is already in use"},
                                status=400,
                            )
                        staff_kwargs["employee_id"] = employee_id

                    if joining_date:
                        staff_kwargs["joining_date"] = joining_date

                    if id_proof_type:
                        staff_kwargs["id_proof_type"] = id_proof_type

                    if id_proof_number:
                        staff_kwargs["id_proof_number"] = id_proof_number

                    staff = Staff(**staff_kwargs)

                    if photo:
                        staff.photo = photo

                    if id_proof_image:
                        staff.id_proof_image = id_proof_image

                    try:
                        staff.save()
                    except IntegrityError as e:
                        err_str = str(e).lower()
                        if "employee_id" in err_str:
                            return JsonResponse(
                                {"error": f"Employee ID '{employee_id}' is already in use"},
                                status=400,
                            )
                        elif "username" in err_str or "email" in err_str:
                            return JsonResponse(
                                {"error": "A staff member with this email already exists"},
                                status=400,
                            )
                        else:
                            return JsonResponse(
                                {"error": "A database conflict occurred. Please try again."},
                                status=400,
                            )

                except Exception:
                    user.delete()
                    raise

        try:
            send_mail(
                subject="Staff Account Created",
                message=(
                    f"Hello {name},\n\n"
                    f"Your staff account has been created.\n\n"
                    f"Login Details:\n"
                    f"Email:    {email}\n"
                    f"Password: {password}\n\n"
                    f"Please change your password after your first login.\n\n"
                    f"Regards,\n{hotel.hotel_name} Management"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
        except Exception as e:
            print("Email send error:", e)

        return JsonResponse({
            "success":      True,
            "staff_id":     staff.id,
            "employee_id":  staff.employee_id,
            "name":         staff.name,
            "department":   staff.department.name if staff.department else None,
            "joining_date": str(staff.joining_date) if staff.joining_date else None,
            "has_photo":    bool(staff.photo),
            "has_id_proof": bool(staff.id_proof_image),
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

                hotel_name     = hotel.hotel_name if hotel else "N/A"
                request_host   = request.get_host()
                request_scheme = request.scheme

                def abs_url(field):
                    if field:
                        try:
                            return f"{request_scheme}://{request_host}{field.url}"
                        except Exception:
                            pass
                    return None

                def get_field_value(obj, field_name):
                    try:
                        val = obj.__dict__.get(field_name)
                        if val is None:
                            return ""
                        return str(val)
                    except Exception:
                        return ""

                def fmt_date(val):
                    if not val:
                        return None
                    if isinstance(val, str):
                        return val
                    try:
                        return val.strftime("%Y-%m-%d")
                    except Exception:
                        return str(val)

                def fmt_datetime(val):
                    if not val:
                        return None
                    if isinstance(val, str):
                        return val
                    try:
                        return val.isoformat()
                    except Exception:
                        return str(val)

                def get_id_proof_label(s):
                    try:
                        field   = s._meta.get_field('id_proof_type')
                        choices = getattr(field, 'choices', None)
                        if choices:
                            val = get_field_value(s, 'id_proof_type')
                            return dict(choices).get(val, val) or 'ID Proof'
                    except Exception:
                        pass
                    return get_field_value(s, 'id_proof_type') or 'ID Proof'

                photo_url = abs_url(staff.photo)
                id_proof_image_url = abs_url(staff.id_proof_image)
                hotel_logo_url = abs_url(hotel.logo)
                face_photo_url = abs_url(getattr(staff, 'face_photo', None))
                face_registered_at = fmt_datetime(getattr(staff, 'face_registered_at', None))

                id_cards = []

                if hasattr(staff, 'documents'):
                    for doc in staff.documents.all():
                        id_cards.append({
                            'id':            doc.id,
                            'document_type': doc.document_type,
                            'url':           abs_url(doc.document),
                            'uploaded_at':   fmt_datetime(doc.uploaded_at),
                        })

                if staff.id_proof_image:
                    id_cards.append({
                        'id':              staff.id,
                        'document_type':   get_id_proof_label(staff),
                        'url':             id_proof_image_url,
                        'uploaded_at':     fmt_datetime(staff.created_at),
                        'id_proof_number': get_field_value(staff, 'id_proof_number'),
                    })

                created_at_val = None

                for field_name in ('created_at', 'date_joined', 'updated_at'):
                    val = staff.__dict__.get(field_name)
                    if val:
                        created_at_val = fmt_datetime(val)
                        break

                if not created_at_val and staff.user:
                    val = getattr(staff.user, 'date_joined', None)
                    if val:
                        created_at_val = fmt_datetime(val)

                dob_val = staff.__dict__.get('dob')

                return JsonResponse({
                    "success": True,
                    "staff": {
                        "id":           staff.id,
                        "employee_id":  get_field_value(staff, 'employee_id'),
                        "name":         get_field_value(staff, 'name'),
                        "email":        str(staff.user.email) if staff.user else "",
                        "phone":        get_field_value(staff, 'phone'),

                        "nickname":     get_field_value(staff, 'nickname'),
                        "dob":          fmt_date(dob_val),
                        "gender":       get_field_value(staff, 'gender'),
                        "address":      get_field_value(staff, 'address'),

                        "emergency_contact_name":  get_field_value(staff, 'emergency_contact_name'),
                        "emergency_contact_phone": get_field_value(staff, 'emergency_contact_phone'),

                        "employment_type": get_field_value(staff, 'employment_type'),

                        "bank_account": get_field_value(staff, 'bank_account'),
                        "ifsc":         get_field_value(staff, 'ifsc'),
                        "pf_number":    get_field_value(staff, 'pf_number'),
                        "esi_number":   get_field_value(staff, 'esi_number'),

                        "notes":        get_field_value(staff, 'notes'),

                        "department_id":   staff.department.id if staff.department else None,
                        "department_name": str(staff.department.name) if staff.department else "N/A",
                        "role":            str(staff.user.role.name) if staff.user and staff.user.role else "Staff",
                        "salary":          float(staff.salary) if staff.salary else 0,
                        "joining_date":    fmt_date(staff.__dict__.get('joining_date')),
                        "created_at":      created_at_val,
                        "is_active":       staff.is_active,
                        "is_available":    staff.is_available,

                        "hotel_name":      str(hotel_name),
                        "hotel_id":        hotel.id if hotel else None,
                        "hotel_logo_url":  hotel_logo_url,

                        "photo_url":       photo_url,
                        "face_photo_url":       face_photo_url,
                        "face_registered_at":   face_registered_at,

                        "id_proof_type":       get_field_value(staff, 'id_proof_type'),
                        "id_proof_type_label": get_id_proof_label(staff),
                        "id_proof_number":     get_field_value(staff, 'id_proof_number'),
                        "id_proof_image_url":  id_proof_image_url,
                    },

                    "id_cards": id_cards
                })

            except Staff.DoesNotExist:
                return JsonResponse({"error": "Staff not found", "success": False}, status=404)

    except Hotel.DoesNotExist:
        return JsonResponse({"error": "Hotel not found", "success": False}, status=404)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e), "success": False}, status=500)
@csrf_exempt
def get_staff(request):
    try:
        current_tenant = connection.tenant

        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)

        with schema_context(current_tenant.schema_name):
            staffs = Staff.objects.filter(hotel=hotel).select_related('department', 'user')

            role_permissions    = RolePermission.objects.select_related('permission', 'role')
            dept_permissions_map = {}
            for rp in role_permissions:
                dept_permissions_map.setdefault(rp.role_id, []).append(rp.permission.name)

            def safe_str(val):
                if val is None:
                    return ""
                if isinstance(val, str):
                    return val
                return str(val)

            def get_id_proof_label(s):
                try:
                    field   = s._meta.get_field('id_proof_type')
                    choices = getattr(field, 'choices', None)
                    if choices:
                        return dict(choices).get(safe_str(s.id_proof_type), safe_str(s.id_proof_type))
                except Exception:
                    pass
                return safe_str(s.id_proof_type)

            hotel_name = hotel.hotel_name if hotel else "N/A"
            staff_list = []

            for s in staffs:
                dept = s.department
                staff_list.append({
                    "id":          s.id,
                    "employee_id": safe_str(s.employee_id),
                    "name":        safe_str(s.name),
                    "email":       safe_str(s.user.email) if s.user else "",
                    "phone":       safe_str(s.phone),
                    "department_id":   dept.id   if dept else None,
                    "department_name": safe_str(dept.name) if dept else "N/A",
                    "department": {
                        "id":          dept.id   if dept else None,
                        "name":        safe_str(dept.name) if dept else "N/A",
                        "permissions": dept_permissions_map.get(dept.id, []) if dept else [],
                    },
                    "role":         safe_str(s.user.role.name) if s.user and s.user.role else "Staff",
                    "salary":       str(s.salary),
                    "joining_date": s.joining_date.strftime("%Y-%m-%d") if s.joining_date else "",
                    "photo":        s.photo.url if s.photo else None,
                    "is_active":    s.is_active,
                    "is_available": s.is_available,
                    "hotel_name":   safe_str(hotel_name),
                    "hotel_id":     hotel.id if hotel else None,
                    "id_proof_type":       safe_str(s.id_proof_type),
                    "id_proof_type_label": get_id_proof_label(s),
                    "id_proof_number":     safe_str(s.id_proof_number),
                    "id_proof_image_url":  s.id_proof_image.url if s.id_proof_image else None,
                })

        return JsonResponse({
            "success":    True,
            "count":      len(staff_list),
            "staffs":     staff_list,
            "hotel_name": safe_str(hotel_name),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
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
            data     = json.loads(request.body)
            staff_id = data.get("staff_id")
        else:
            staff_id = request.POST.get("staff_id")

        print("DEBUG staff_id:", staff_id)

        if not staff_id:
            return JsonResponse({"error": "Staff ID required"}, status=400)

        tenant = connection.tenant

        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=tenant.schema_name)

        with schema_context(tenant.schema_name):
            with transaction.atomic():
                staff_obj = Staff.objects.select_related('user').filter(
                    id=staff_id, hotel=hotel
                ).first()

                if not staff_obj:
                    return JsonResponse({"error": "Staff not found"}, status=404)

                user = staff_obj.user
                print(f"DEBUG delete — staff: {staff_obj.name} | user: {user.username if user else None}")

                if user:
                    # Deleting User cascades and auto-deletes Staff
                    # because Staff.user = OneToOneField(User, on_delete=CASCADE)
                    user.delete()
                    print(f"DEBUG delete — user deleted, staff cascade-deleted")
                else:
                    staff_obj.delete()
                    print(f"DEBUG delete — no user linked, staff deleted directly")

        return JsonResponse({
            "success": True,
            "message": "Employee deleted successfully"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@require_POST
def update_staff(request):
    try:
        staff_id = request.POST.get("staff_id")
        if not staff_id:
            return JsonResponse({"error": "Staff ID required"}, status=400)
 
        tenant = connection.tenant
 
        with schema_context('public'):
            hotel = Hotel.objects.get(schema_name=tenant.schema_name)
 
        with schema_context(tenant.schema_name):
            staff_obj = Staff.objects.select_related('department', 'user').filter(
                id=staff_id, hotel=hotel
            ).first()
 
            if not staff_obj:
                return JsonResponse({"error": "Staff not found"}, status=404)
 
            # ----------------------------------------------------------------
            # Helpers
            # ----------------------------------------------------------------
            def parse_date(val):
                if not val:
                    return None
                if hasattr(val, 'strftime'):
                    return val
                try:
                    from datetime import datetime
                    return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
                except ValueError:
                    return None
 
            def fmt_date(val):
                if not val:
                    return None
                if isinstance(val, str):
                    return val
                return val.strftime("%Y-%m-%d")
 
            def safe_str(val):
                if val is None:
                    return ""
                if isinstance(val, str):
                    return val
                return str(val)
 
            def get_id_proof_label(s):
                try:
                    field   = s._meta.get_field('id_proof_type')
                    choices = getattr(field, 'choices', None)
                    if choices:
                        val = safe_str(s.id_proof_type)
                        return dict(choices).get(val, val)
                except Exception:
                    pass
                return safe_str(s.id_proof_type)
 
            # ----------------------------------------------------------------
            # KEY FIX: HTML forms always submit every field even when blank.
            # request.POST.get("field", current) returns "" not the fallback
            # because the key EXISTS in POST — just empty. post_val() only
            # accepts the new value when it is non-empty, so existing DB data
            # is never accidentally wiped by a blank form submission.
            # ----------------------------------------------------------------
            def post_val(key, current):
                v = request.POST.get(key, "").strip()
                return v if v else current
 
            # ----------------------------------------------------------------
            # Simple text / choice fields
            # ----------------------------------------------------------------
            staff_obj.name  = post_val("name",  staff_obj.name)
            staff_obj.phone = post_val("phone", staff_obj.phone)
 
            staff_obj.nickname = post_val("nickname", staff_obj.nickname)
            staff_obj.gender   = post_val("gender",   staff_obj.gender)
            staff_obj.address  = post_val("address",  staff_obj.address)
 
            staff_obj.emergency_contact_name  = post_val("emergency_contact_name",  staff_obj.emergency_contact_name)
            staff_obj.emergency_contact_phone = post_val("emergency_contact_phone", staff_obj.emergency_contact_phone)
 
            staff_obj.employment_type = post_val("employment_type", staff_obj.employment_type)
 
            staff_obj.bank_account = post_val("bank_account", staff_obj.bank_account)
            staff_obj.ifsc         = post_val("ifsc",         staff_obj.ifsc)
            staff_obj.pf_number    = post_val("pf_number",    staff_obj.pf_number)
            staff_obj.esi_number   = post_val("esi_number",   staff_obj.esi_number)
            staff_obj.notes        = post_val("notes",        staff_obj.notes)
 
            staff_obj.id_proof_type   = post_val("id_proof_type",   staff_obj.id_proof_type)
            staff_obj.id_proof_number = post_val("id_proof_number", staff_obj.id_proof_number)
 
            # ----------------------------------------------------------------
            # Salary — keep existing if blank
            # ----------------------------------------------------------------
            salary_raw = request.POST.get("salary", "").strip()
            if salary_raw:
                staff_obj.salary = salary_raw
 
            # ----------------------------------------------------------------
            # Dates — only update when a valid date string is provided
            # ----------------------------------------------------------------
            dob_val = parse_date(request.POST.get("dob", ""))
            if dob_val:
                staff_obj.dob = dob_val
 
            joining_date_val = parse_date(request.POST.get("joining_date", ""))
            if joining_date_val:
                staff_obj.joining_date = joining_date_val
 
            # ----------------------------------------------------------------
            # Employee ID — unique-check before accepting
            # ----------------------------------------------------------------
            new_employee_id = request.POST.get("employee_id", "").strip()
            if new_employee_id and new_employee_id != staff_obj.employee_id:
                if Staff.objects.filter(hotel=hotel, employee_id=new_employee_id).exclude(id=staff_obj.id).exists():
                    return JsonResponse(
                        {"error": f"Employee ID '{new_employee_id}' is already in use"},
                        status=400,
                    )
                staff_obj.employee_id = new_employee_id
 
            # ----------------------------------------------------------------
            # Department
            # ----------------------------------------------------------------
            dept_id = request.POST.get("department", "").strip()
            if dept_id:
                try:
                    dept = Department.objects.filter(id=int(dept_id)).first()
                    if dept:
                        staff_obj.department = dept
                    else:
                        return JsonResponse({"error": "Department not found"}, status=400)
                except (ValueError, TypeError):
                    pass
 
            # ----------------------------------------------------------------
            # File uploads — only replace when a new file is actually sent
            # ----------------------------------------------------------------
            if request.FILES.get("photo"):
                staff_obj.photo = request.FILES["photo"]
            if request.FILES.get("id_proof_image"):
                staff_obj.id_proof_image = request.FILES["id_proof_image"]
 
            staff_obj.save()
 
            # ----------------------------------------------------------------
            # User / email update
            # ----------------------------------------------------------------
            if staff_obj.user:
                new_email = request.POST.get("email", "").strip()
                if new_email and new_email != staff_obj.user.email:
                    new_username = f"{new_email}_{hotel.id}"
                    if not User.objects.filter(username=new_username).exclude(pk=staff_obj.user.pk).exists():
                        staff_obj.user.email    = new_email
                        staff_obj.user.username = new_username
                        staff_obj.user.save(update_fields=['email', 'username'])
                    else:
                        return JsonResponse(
                            {"error": "Another account with this email already exists"},
                            status=400,
                        )
 
            # ----------------------------------------------------------------
            # Role name
            # ----------------------------------------------------------------
            role_name = "Staff"
            try:
                if staff_obj.user and staff_obj.user.role:
                    role_name = safe_str(staff_obj.user.role.name)
            except Exception:
                pass
 
            # ----------------------------------------------------------------
            # Response
            # ----------------------------------------------------------------
            return JsonResponse({
                "success": True,
                "message": "Staff updated successfully",
                "staff": {
                    "id":                      staff_obj.id,
                    "name":                    safe_str(staff_obj.name),
                    "email":                   safe_str(staff_obj.user.email) if staff_obj.user else "",
                    "phone":                   safe_str(staff_obj.phone),
                    "employee_id":             safe_str(staff_obj.employee_id),
                    "nickname":                safe_str(staff_obj.nickname),
                    "dob":                     fmt_date(staff_obj.dob),
                    "gender":                  safe_str(staff_obj.gender),
                    "address":                 safe_str(staff_obj.address),
                    "joining_date":            fmt_date(staff_obj.joining_date),
                    "emergency_contact_name":  safe_str(staff_obj.emergency_contact_name),
                    "emergency_contact_phone": safe_str(staff_obj.emergency_contact_phone),
                    "employment_type":         safe_str(staff_obj.employment_type),
                    "bank_account":            safe_str(staff_obj.bank_account),
                    "ifsc":                    safe_str(staff_obj.ifsc),
                    "pf_number":               safe_str(staff_obj.pf_number),
                    "esi_number":              safe_str(staff_obj.esi_number),
                    "notes":                   safe_str(staff_obj.notes),
                    "department":              safe_str(staff_obj.department.name) if staff_obj.department else None,
                    "department_id":           staff_obj.department.id if staff_obj.department else None,
                    "salary":                  str(staff_obj.salary),
                    "role":                    role_name,
                    "id_proof_type":           safe_str(staff_obj.id_proof_type),
                    "id_proof_type_label":     get_id_proof_label(staff_obj),
                    "id_proof_number":         safe_str(staff_obj.id_proof_number),
                },
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
    from pms.models import Room, RoomUnit, RoomImage,Property
    from django.utils import timezone
    from django.contrib.auth import update_session_auth_hash
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
                hotel.email         = request.POST.get('email',          hotel.email)
                hotel.description   = request.POST.get('description',   hotel.description)
                hotel.property_type = request.POST.get('property_type', hotel.property_type)
                if request.FILES.get('logo'):
                    hotel.logo = request.FILES['logo']
                if request.FILES.get('image'):
                    hotel.image = request.FILES['image']
                hotel.save()

            # ── Optional password change ──────────────────────────────
            new_password = request.POST.get('new_password', '').strip()
            if new_password:
                current_password = request.POST.get('current_password', '').strip()
                confirm_password  = request.POST.get('confirm_password', '').strip()

                if not current_password:
                    return JsonResponse({'success': False, 'error': 'Enter your current password.'}, status=400)

                if not request.user.check_password(current_password):
                    return JsonResponse({'success': False, 'error': 'Current password is incorrect.'}, status=400)

                if new_password != confirm_password:
                    return JsonResponse({'success': False, 'error': 'New passwords do not match.'}, status=400)

                if len(new_password) < 8:
                    return JsonResponse({'success': False, 'error': 'New password must be at least 8 characters.'}, status=400)

                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)

            return JsonResponse({'success': True})

        elif form_type == 'room_details':
            try:
                with transaction.atomic():
                    room_type        = request.POST.get('room_type')
                    custom_room_type = request.POST.get('custom_room_type', '').strip()

                    if room_type == 'Custom' and not custom_room_type:
                        return JsonResponse({'success': False, 'error': 'Custom room type name is required.'}, status=400)

                    # ── FEATURES (NEW) ──────────────────────────────
                    # Accepts multiple form fields: features=WiFi&features=AC&features=TV
                    # Falls back to a comma-separated single field if that's what's sent.
                    features = request.POST.getlist('features')
                    if not features:
                        raw_features = request.POST.get('features', '')
                        if raw_features:
                            features = [f.strip() for f in raw_features.split(',') if f.strip()]

                    room = Room.objects.create(
                        room_type=room_type,
                        custom_room_type=custom_room_type if room_type == 'Custom' else '',
                        base_price=request.POST.get('base_price') or 0,
                        max_adults=request.POST.get('max_adults') or 2,
                        max_children=request.POST.get('max_children') or 0,
                        description=request.POST.get('description') or '',
                        extra_adult_price=request.POST.get('extra_adult_price') or 0,
                        extra_child_price=request.POST.get('extra_child_price') or 0,
                        overstay_price=request.POST.get('overstay_price') or 0,        # NEW
                        features=features,                                      # NEW
                    )

                    # ── AMENITIES ────────────────────────────────────
                    # The frontend wizard can still send stale/placeholder IDs
                    # that don't correspond to any real Property row. Filtering
                    # through Property.objects.filter(id__in=...) before calling
                    # .set() means those bad IDs are silently dropped instead of
                    # raising a ForeignKey IntegrityError and 500ing the whole
                    # room save.
                    amenity_ids = request.POST.getlist('amenities')
                    if amenity_ids:
                        valid_amenities = Property.objects.filter(id__in=amenity_ids)
                        room.amenities.set(valid_amenities)

                    total_units = int(request.POST.get('total_units') or 1)
                    prefix_map  = {
                        'Single': 'S',
                        'Double': 'D',
                        'Deluxe': 'DL',
                        'Suite':  'SU',
                        'Custom': (custom_room_type[:2].upper() if custom_room_type else 'CR'),
                    }
                    prefix = prefix_map.get(room_type, 'R')

                    existing_numbers = set(RoomUnit.objects.values_list('room_number', flat=True))
                    units, counter = [], 1
                    while len(units) < total_units:
                        number = f'{prefix}{counter}'
                        if number not in existing_numbers:
                            units.append(RoomUnit(room=room, room_number=number))
                        counter += 1

                    RoomUnit.objects.bulk_create(units)

                    for i, img in enumerate(request.FILES.getlist('images')):
                        RoomImage.objects.create(room=room, image=img, is_primary=(i == 0))

                    asset_ids = request.POST.getlist('asset_ids')
                    if asset_ids:
                        from inventory.models import HotelAsset, AssetLocation

                        assets = HotelAsset.objects.filter(id__in=asset_ids)
                        for asset in assets:
                            # Reset ALL previous location records — no stale is_current=True rows
                            AssetLocation.objects.filter(asset=asset).update(is_current=False)

                            # Create new current AssetLocation for this room
                            AssetLocation.objects.create(
                                asset=asset,
                                room=room,
                                room_unit=None,
                                area="",
                                is_current=True,
                            )

                            # Keep HotelAsset direct fields in sync
                            asset.room        = room
                            asset.room_unit   = None
                            asset.area        = ""
                            asset.save()

                return JsonResponse({
                    'success':      True,
                    'room_id':      room.id,
                    'display_type': room.display_type(),
                    'features':     room.features,                             # NEW
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
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
    if subscription_plan and not subscription_plan.is_active:
        subscription_plan = None

    active_plan_name  = subscription_plan.name  if subscription_plan else None
    active_plan_price = subscription_plan.price if subscription_plan else None

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

    active_modules_count     = len(active_modules)
    subscription_expiry      = hotel.subscription_expiry
    subscription_expiry_date = None
    expiry_days_remaining    = 0

    if subscription_expiry:
        subscription_expiry_date = subscription_expiry
        expiry_days_remaining    = max(0, (subscription_expiry_date - today).days)

    subscription_status = hotel.subscription_status or ''

    is_actively_subscribed = (
        subscription_status == 'active'
        and hotel.is_subscribed
        and subscription_expiry_date is not None
        and subscription_expiry_date >= today
    )

    should_show_plans = (
        not is_actively_subscribed
        or (subscription_expiry_date and (subscription_expiry_date - today).days <= 7)
    )

    show_subscription_gate = (
        not hotel.is_on_trial
        and not hotel.is_subscribed
        and subscription_status == 'expired'
    )

    show_trial_banner  = hotel.is_on_trial and not show_subscription_gate

    show_expiry_warning = (
        hotel.is_subscribed
        and not show_subscription_gate
        and not show_trial_banner
        and 0 < expiry_days_remaining <= 7
    )

    can_start_trial = (
        hotel.trial_eligible
        and not hotel.is_on_trial
        and not hotel.is_subscribed
        and subscription_status not in ('active',)
    )

    from inventory.models import AssetCategory, AssetLocation
    asset_categories = list(AssetCategory.objects.values('id', 'name').order_by('name'))

    # ── NEW: Fetch existing rooms for "View Rooms" tab ──────────────────
    existing_rooms_data = []
    with schema_context(current_tenant.schema_name):
        existing_rooms = Room.objects.filter(is_active=True).prefetch_related('images', 'amenities')
        for r in existing_rooms:
            primary_image = r.images.filter(is_primary=True).first() or r.images.first()

            # Pull assets currently linked to this room (best-effort), as {id, name}
            asset_objs = []
            try:
                locations = (
                    AssetLocation.objects
                    .filter(room=r, is_current=True)
                    .select_related('asset')
                )
                for loc in locations:
                    if loc.asset:
                        asset_objs.append({'id': loc.asset.id, 'name': loc.asset.name})
            except Exception:
                pass

            amenity_ids = list(r.amenities.values_list('id', flat=True))

            existing_rooms_data.append({
                'id':          r.id,
                'type':        (r.custom_room_type if r.room_type == 'Custom' and r.custom_room_type else r.room_type),
                'units':       r.units.count(),
                'price':       str(r.base_price),
                'adults':      r.max_adults,
                'children':    r.max_children,
                'description': r.description or '',
                'overstay_price': str(r.overstay_price),        # NEW
                'assets':      asset_objs,
                'amenity_ids': amenity_ids,
                'features':    r.features or [],
                'image_url':   primary_image.image.url if primary_image else None,
            })

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
        'is_actively_subscribed': is_actively_subscribed,
        'should_show_plans':      should_show_plans,
        'can_start_trial':        can_start_trial,
        'trial_days':             hotel.trial_days or 14,
        'show_plan':              not hotel.is_subscribed and not hotel.is_on_trial,
        'asset_categories':       asset_categories,
        'existing_rooms_json':    json.dumps(existing_rooms_data),
        'amenities':              Property.objects.all(),
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
@require_POST
@login_required
def set_plan_trial_days(request, plan_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        data = json.loads(request.body)
        days = data.get("trial_days")

        if not days or int(days) < 1:
            return JsonResponse({"error": "trial_days must be at least 1."}, status=400)

        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.trial_days = int(days)
        plan.save(update_fields=['trial_days'])

        return JsonResponse({
            "success":    True,
            "plan":       plan.name,
            "trial_days": plan.trial_days,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@require_POST
@login_required
def toggle_plan_status(request, plan_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.is_active = not plan.is_active
        plan.save(update_fields=['is_active'])
        return JsonResponse({
            "success":   True,
            "plan":      plan.name,
            "is_active": plan.is_active,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
@login_required
def set_plan_expiry(request, plan_id):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        from datetime import date
        data            = json.loads(request.body)
        expiry_str      = data.get("valid_until", "").strip()
        plan            = get_object_or_404(SubscriptionPlan, id=plan_id)

        if expiry_str:
            expiry = date.fromisoformat(expiry_str)
            if expiry < date.today():
                return JsonResponse({"error": "Expiry date cannot be in the past."}, status=400)
            plan.valid_until = expiry
        else:
            plan.valid_until = None   

        plan.save(update_fields=['valid_until'])
        return JsonResponse({
            "success":     True,
            "plan":        plan.name,
            "valid_until": str(plan.valid_until) if plan.valid_until else None,
        })
    except ValueError:
        return JsonResponse({"error": "Date must be YYYY-MM-DD format."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@require_POST
@login_required
def tenant_create_payment(request):
    """
    Called from the hotel setup wizard (tenant side).
    Identifies the hotel via the current tenant schema — no hotel_id needed.
    """
    try:
        data = json.loads(request.body)
        current_tenant = connection.tenant

        with schema_context('public'):
            hotel = get_object_or_404(Hotel, schema_name=current_tenant.schema_name)

            plan_name = data.get('plan_name', '').strip()
            if not plan_name:
                return JsonResponse({"error": "No plan selected."}, status=400)

            plan = SubscriptionPlan.objects.filter(name=plan_name, is_active=True).first()
            if not plan:
                return JsonResponse({"error": "Plan not found."}, status=400)

            
            price = plan.price
            coupon_code = data.get('coupon')
            discount = 0
            if coupon_code:
               
                pass

            final_amount = price - discount

           
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

            _enable_plan_modules(hotel, plan)

            # Record the payment
            payment = PlanPayment.objects.create(
                hotel    = hotel,
                plan     = plan,
                amount   = final_amount,
                status   = 'paid',
                due_date = timezone.now().date() + relativedelta(months=1),
                paid_date = timezone.now().date(),
                notes    = f"payment_method={data.get('payment_method','card')}",
            )

        try:
            send_mail(
                subject="Subscription Activated 🎉",
                message=(
                    f"Hello {hotel.hotel_name},\n\n"
                    f"Your subscription to the {plan.name} plan is now active.\n"
                    f"Amount paid: ₹{final_amount}\n"
                    f"Valid until: {hotel.subscription_expiry.strftime('%d %b %Y')}\n\n"
                    "Regards,\nHotelCloud Team"
                ),
                from_email=None,
                recipient_list=[hotel.email],
                fail_silently=True,
            )
        except Exception:
            pass

        return JsonResponse({
            "success":  True,
            "plan":     plan.name,
            "expiry":   hotel.subscription_expiry.strftime("%d %b %Y"),
            "payment_id": payment.id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

from django.contrib.auth.views import PasswordResetConfirmView
class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'auth/password_reset_confirm.html'

    def get_success_url(self):
        user = self.user
        if hasattr(user, 'staff_profile'):
            return '/staff-login/'
        return '/login/'


import base64
from django.core.files.base import ContentFile
from django.views.decorators.csrf import ensure_csrf_cookie


@login_required
@require_POST
def register_staff_face(request, staff_id):
    """Save face descriptor (128 floats) + snapshot for a staff member.
    Accepts multipart (photo file + descriptor JSON string) or JSON (photo_base64)."""
    staff = Staff.objects.filter(id=staff_id).first()
    if not staff:
        return JsonResponse({"success": False, "error": "Staff not found"}, status=404)

    photo_file = None
    photo_b64 = None

    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        descriptor = data.get("descriptor")
        photo_b64 = data.get("photo_base64")
    else:
        raw = request.POST.get("descriptor")
        try:
            descriptor = json.loads(raw) if raw else None
        except ValueError:
            descriptor = None
        photo_file = request.FILES.get("photo")

    try:
        descriptor = [float(x) for x in descriptor]
    except (TypeError, ValueError):
        descriptor = None
    if not descriptor or len(descriptor) != 128:
        return JsonResponse({"success": False, "error": "Invalid face data."}, status=400)

    if photo_file:
        if photo_file.size > 5 * 1024 * 1024:
            return JsonResponse({"success": False, "error": "Photo is too large."}, status=400)
        if not (photo_file.content_type or "").startswith("image/"):
            return JsonResponse({"success": False, "error": "File must be an image."}, status=400)

    try:
        if photo_file or photo_b64:
            if staff.face_photo:
                staff.face_photo.delete(save=False)   # remove the old snapshot
            if photo_file:
                staff.face_photo.save(f"staff_{staff.id}_face.jpg", photo_file, save=False)
            else:
                fmt, imgstr = photo_b64.split(";base64,")
                ext = fmt.split("/")[-1] or "jpg"
                staff.face_photo.save(
                    f"staff_{staff.id}_face.{ext}",
                    ContentFile(base64.b64decode(imgstr)),
                    save=False,
                )

        staff.face_descriptor = descriptor
        staff.face_registered_at = timezone.now()
        staff.save(update_fields=["face_descriptor", "face_photo", "face_registered_at"])

        return JsonResponse({
            "success": True,
            "message": "Face registered successfully",
            "face_photo_url": staff.face_photo.url if staff.face_photo else "",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@login_required
def staff_directory_page(request):
    current_tenant = connection.tenant

    with schema_context('public'):
        hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)

    with schema_context(current_tenant.schema_name):
        staffs = (
            Staff.objects.filter(hotel=hotel)
            .select_related('department', 'user')
            .order_by('employee_id')
        )
        departments = Department.objects.filter(hotel=hotel)

        total_staff = staffs.count()
        active_staff = staffs.filter(is_active=True).count()
        total_departments = departments.count()

        salaries = [s.salary for s in staffs if s.salary]
        average_salary = sum(salaries) / len(salaries) if salaries else 0

    return render(request, "hotel/staff_directory.html", {
        "hotel": hotel,
        "staffs": staffs,
        "departments": departments,
        "total_staff": total_staff,
        "active_staff": active_staff,
        "total_departments": total_departments,
        "average_salary": average_salary,
    })


def _file_url(value):
    try:
        return value.url if value and value.name else ""
    except Exception:
        return ""


def _display_date(value):
    if not value:
        return ""
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def _display_datetime(value):
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime") else str(value)


@login_required
@ensure_csrf_cookie
def staff_details_page(request, staff_id):
    """Render the HTML profile page; keep get_staff_details as the JSON API."""
    obj = get_object_or_404(
        Staff.objects.select_related("user", "department", "hotel"), pk=staff_id
    )
    user = getattr(obj, "user", None)
    hotel = getattr(obj, "hotel", None)
    department = getattr(obj, "department", None)
    role_obj = getattr(user, "role", None)

    cards = []
    # Support either related_name used by the project (documents or id_cards).
    for related_name in ("documents", "id_cards"):
        manager = getattr(obj, related_name, None)
        if manager is None or not hasattr(manager, "all"):
            continue
        for card in manager.all():
            image = getattr(card, "document", None) or getattr(card, "image", None)
            cards.append({
                "id": getattr(card, "id", None),
                "document_type": getattr(card, "document_type", "ID document"),
                "id_proof_number": getattr(card, "id_proof_number", ""),
                "uploaded_at": _display_datetime(getattr(card, "uploaded_at", None)),
                "url": _file_url(image),
            })
        break

    id_proof_image_url = _file_url(getattr(obj, "id_proof_image", None))
    created_at = getattr(obj, "created_at", None) or getattr(user, "date_joined", None)
    id_proof_type = getattr(obj, "id_proof_type", "") or ""
    id_proof_label = id_proof_type
    try:
        field = obj._meta.get_field("id_proof_type")
        if field.choices:
            id_proof_label = dict(field.choices).get(id_proof_type, id_proof_type)
    except Exception:
        pass

    staff = {
        "id": obj.pk,
        "employee_id": getattr(obj, "employee_id", ""),
        "name": getattr(obj, "name", ""),
        "email": getattr(user, "email", "") if user else "",
        "phone": getattr(obj, "phone", ""),
        "nickname": getattr(obj, "nickname", ""),
        "dob": _display_date(getattr(obj, "dob", None)),
        "gender": getattr(obj, "gender", ""),
        "address": getattr(obj, "address", ""),
        "emergency_contact_name": getattr(obj, "emergency_contact_name", ""),
        "emergency_contact_phone": getattr(obj, "emergency_contact_phone", ""),
        "employment_type": getattr(obj, "employment_type", ""),
        "bank_account": getattr(obj, "bank_account", ""),
        "ifsc": getattr(obj, "ifsc", ""),
        "pf_number": getattr(obj, "pf_number", ""),
        "esi_number": getattr(obj, "esi_number", ""),
        "notes": getattr(obj, "notes", ""),
        "department_id": getattr(obj, "department_id", None),
        "department": getattr(department, "name", "Unassigned") if department else "Unassigned",
        "role": getattr(role_obj, "name", None) or "Staff",
        "salary": getattr(obj, "salary", 0) or 0,
        "joining_date": _display_date(getattr(obj, "joining_date", None)),
        "created_at": _display_datetime(created_at),
        "is_active": getattr(obj, "is_active", True),
        "is_available": getattr(obj, "is_available", False),
        "hotel_name": getattr(hotel, "hotel_name", "N/A") if hotel else "N/A",
        "hotel_id": getattr(hotel, "id", None) if hotel else None,
        "hotel_logo_url": _file_url(getattr(hotel, "logo", None)) if hotel else "",
        "photo_url": _file_url(getattr(obj, "photo", None)),
        "face_photo_url": _file_url(getattr(obj, "face_photo", None)),
        "face_registered_at": _display_datetime(getattr(obj, "face_registered_at", None)),
        "id_proof_type": id_proof_type,
        "id_proof_type_label": id_proof_label,
        "id_proof_number": getattr(obj, "id_proof_number", ""),
        "id_proof_image_url": id_proof_image_url,
        "id_proof_url": id_proof_image_url,
        "id_proof_uploaded_at": _display_datetime(created_at) if id_proof_image_url else "",
        "id_cards": cards,
    }
    return render(request, "hotel/staff_details.html", {"staff": staff})

@login_required
@never_cache
def add_staff_page(request):
    hotel_id = request.session.get("hotel_id")

    departments_qs = Department.objects.all().order_by("name")
    if hotel_id:
        departments_qs = departments_qs.filter(hotel_id=hotel_id)

    return render(
        request,
        "hotel/staff_add_stepper.html",
        {
            "departments": departments_qs,
        },
    )

@login_required
@never_cache
def department_page(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        messages.error(request, "Hotel session expired. Please log in again.")
        return redirect("hotel_login")

    hotel_obj = get_object_or_404(Hotel, id=hotel_id)

    # Departments that require a module the hotel's plan may not include.
    gated_departments = {"maintenance", "security"}

    with schema_context(hotel_obj.schema_name):
        active_module_names = set(
            HotelModule.objects.filter(hotel=hotel_obj, is_enabled=True)
            .select_related('module')
            .values_list('module__name', flat=True)
        )
    active_module_names_lower = {n.strip().lower() for n in active_module_names}

    locked_departments = sorted(
        name for name in gated_departments
        if name not in active_module_names_lower
    )

    if request.method == "POST":
        department_name = request.POST.get("name", "").strip()

        if not department_name:
            messages.error(request, "Please select a department.")
            return redirect("department_page")

        if department_name.strip().lower() in locked_departments:
            messages.error(
                request,
                f"{department_name} isn't included in your current plan. Upgrade to add this department."
            )
            return redirect("department_page")

        exists = Department.objects.filter(
            hotel=hotel_obj, name__iexact=department_name
        ).exists()

        if exists:
            messages.warning(request, f"{department_name} department already exists.")
        else:
            Department.objects.create(hotel=hotel_obj, name=department_name)
            messages.success(request, f"{department_name} department created successfully.")

        return redirect("department_page")

    departments = list(
        Department.objects.filter(hotel=hotel_obj).order_by("name")
    )

    total_staff = Staff.objects.filter(hotel=hotel_obj).count()

    dept_presets = {
        "front desk":   {"icon": "🛎", "color": "green",  "description": "Guest services and reception operations"},
        "housekeeping": {"icon": "🧹", "color": "blue",   "description": "Room cleaning and maintenance"},
        "hr":           {"icon": "⚙",  "color": "orange", "description": "Human resources and staff management"},
        "restaurant":   {"icon": "🍴", "color": "purple", "description": "Food & beverage and restaurant operations"},
        "maintenance":  {"icon": "🔧", "color": "orange", "description": "Facility upkeep and repairs"},
        "security":     {"icon": "🛡",  "color": "blue",   "description": "Property and guest safety"},
    }
    default_preset = {"icon": "▦", "color": "purple", "description": "Department operations"}

    for department in departments:
        department.staff_count = Staff.objects.filter(
            hotel=hotel_obj, department=department
        ).count()

        preset = dept_presets.get(department.name.strip().lower(), default_preset)
        department.icon = preset["icon"]
        department.color = preset["color"]
        if not getattr(department, "description", None):
            department.description = preset["description"]

        lead = (
            Staff.objects.filter(hotel=hotel_obj, department=department, is_active=True)
            .select_related("user")
            .order_by("id")
            .first()
        )
        if lead:
            name_parts = (lead.name or "").split()
            initials = "".join(p[0] for p in name_parts[:2]).upper() or "?"
            department.lead_name = lead.name
            department.lead_role = f"{department.name} Staff"
            department.lead_initials = initials
        else:
            department.lead_name = None
            department.lead_role = None
            department.lead_initials = None

    total_departments = len(departments)
    average_team_size = (
        f"{round(total_staff / total_departments, 1)} staff"
        if total_departments else "0 staff"
    )

    return render(
        request,
        "hotel/departments_updated.html",
        {
            "departments": departments,
            "total_staff": total_staff,
            "total_departments": total_departments,
            "average_team_size": average_team_size,
            "locked_departments": locked_departments,
        },
    )


@login_required
@require_POST
def delete_department(request, department_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Hotel session expired."}, status=401)

    department = get_object_or_404(
        Department,
        id=department_id,
        hotel_id=hotel_id,
    )

    department_name = department.name
    department.delete()

    return JsonResponse(
        {
            "success": True,
            "message": f"{department_name} deleted successfully.",
        }
    )
def _sync_domain_with_hotel_name(hotel):
    """Keep Client.name and the primary domain in step with hotel.hotel_name.
    schema_name is NOT changed (renaming a Postgres schema is risky).

    Returns (domain, changed):
        domain  -> the tenant's primary domain string (or None if not found)
        changed -> True only if the domain was actually rewritten just now
    """
    with schema_context('public'):
        client = Client.objects.filter(schema_name=hotel.schema_name).first()
        if not client:
            return None, False

        if client.name != hotel.hotel_name:
            client.name = hotel.hotel_name
            client.save(update_fields=['name'])

        domain_obj = (
            Domain.objects.filter(tenant=client, is_primary=True).first()
            or Domain.objects.filter(tenant=client).first()
        )
        if not domain_obj:
            return None, False

        base = slugify(hotel.hotel_name) or "hotel"
        candidate = f"{base}.{settings.BASE_URL}"
        counter = 1
        # keep it unique, ignoring this tenant's own current domain
        while Domain.objects.filter(domain=candidate).exclude(pk=domain_obj.pk).exists():
            candidate = f"{base}{counter}.{settings.BASE_URL}"
            counter += 1

        changed = domain_obj.domain != candidate
        if changed:
            domain_obj.domain = candidate
            domain_obj.is_primary = True
            domain_obj.save()

        return domain_obj.domain, changed


from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from django_tenants.utils import schema_context

# from .models import Hotel


def _error(message, status=400):
    return JsonResponse({"success": False, "error": message}, status=status)


@never_cache
@login_required
def hotel_details_page(request):

    # ── Current hotel ─────────────────────────────────────────
    current_tenant = connection.tenant

    try:
        with schema_context("public"):
            hotel = get_object_or_404(
                Hotel.objects.select_related("subscription_plan"),
                schema_name=current_tenant.schema_name,
            )
    except Exception as e:
        print("HOTEL LOAD ERROR:", repr(e))
        if request.method == "POST":
            return _error(f"Unable to load hotel: {e}", 500)
        raise

    # ── POST: update hotel ────────────────────────────────────
    if request.method == "POST":
        try:
            get = lambda key: (request.POST.get(key) or "").strip()

            hotel_name    = get("hotel_name")
            owner_name    = get("owner_name")
            property_type = get("property_type")
            phone         = get("phone")
            email         = get("email")
            description   = get("description")
            address       = get("address")
            city          = get("city")
            state         = get("state")

            if not hotel_name:
                return _error("Hotel name is required.")
            if not owner_name:
                return _error("Owner name is required.")

            # ── Password: OPTIONAL ────────────────────────────
            current_password = request.POST.get("current_password") or ""
            new_password     = request.POST.get("new_password") or ""
            confirm_password = request.POST.get("confirm_password") or ""

            wants_password_change = bool(new_password or confirm_password)

            # Validate BEFORE saving anything, so a bad password
            # does not leave the form half-saved.
            if wants_password_change:
                if not current_password:
                    return _error("Enter your current password to change it.")
                if not new_password:
                    return _error("Enter a new password.")
                if not confirm_password:
                    return _error("Confirm your new password.")
                if not request.user.check_password(current_password):
                    return _error("Current password is incorrect.")
                if new_password != confirm_password:
                    return _error("New password and confirmation do not match.")
                if len(new_password) < 8:
                    return _error("Password must contain at least 8 characters.")

            # ── Save hotel fields (+ domain sync) ─────────────
            new_redirect_url = None
            with schema_context("public"):
                with transaction.atomic():
                    hotel.hotel_name = hotel_name
                    hotel.owner_name = owner_name

                    if property_type:
                        hotel.property_type = property_type
                    if email:
                        hotel.email = email

                    hotel.phone       = phone
                    hotel.description = description
                    hotel.address     = address
                    hotel.city        = city
                    hotel.state       = state

                    logo = request.FILES.get("logo")
                    if logo:
                        hotel.logo = logo

                    image = request.FILES.get("image")
                    if image:
                        hotel.image = image

                    hotel.save()

                    # Always compare the EXPECTED domain (from the hotel name)
                    # with the ACTUAL primary domain. If they differ, fix it.
                    # This also repairs a domain that was left stale by an
                    # earlier save.
                    new_domain, domain_changed = _sync_domain_with_hotel_name(hotel)
                    print("SYNC: new_domain =", new_domain, "| changed =", domain_changed)
                    if domain_changed:
                        new_redirect_url = f"http://{new_domain}{settings.PORT}"

            # ── Save password (only if requested) ─────────────
            if wants_password_change:
                request.user.set_password(new_password)
                request.user.save(update_fields=["password"])
                update_session_auth_hash(request, request.user)  # stay logged in

            return JsonResponse({
                "success": True,
                "message": "Hotel details updated successfully.",
                "password_changed": wants_password_change,
                "domain_changed": bool(new_redirect_url),
                "redirect_url": (new_redirect_url + "/login/") if new_redirect_url else None,
            })

        except Exception as e:
            import traceback
            print("\n" + "=" * 70)
            print("HOTEL DETAILS UPDATE ERROR")
            print("=" * 70)
            traceback.print_exc()
            print("=" * 70 + "\n")
            return _error(str(e), 500)

    # ── GET: display page ─────────────────────────────────────
    return render(request, "hotel-setup/hotel_details.html", {
        "hotel": hotel,
        "is_first_time": not hotel.is_setup_complete,
    })

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

# Hotel is already imported at the top of your views file:
# from .models import Hotel


# ──────────────────────────────────────────────────────────────
# ASSET <-> ROOM HELPERS
# (also use _link_asset_to_room inside hotel_setup, see bottom)
# ──────────────────────────────────────────────────────────────

def _sync_asset_legacy_fields(asset):
    """Keep HotelAsset.room / room_unit / area in step with its current locations.
    Filled only when the asset has exactly one current location, otherwise cleared."""
    from inventory.models import AssetLocation

    current = list(
        AssetLocation.objects.filter(asset=asset, is_current=True)
        .select_related("room", "room_unit")[:2]
    )
    if len(current) == 1:
        loc = current[0]
        asset.room, asset.room_unit, asset.area = loc.room, loc.room_unit, loc.area or ""
    else:
        asset.room, asset.room_unit, asset.area = None, None, ""
    asset.save(update_fields=["room", "room_unit", "area"])


def _link_asset_to_room(asset, room):
    """Add `room` as a current location WITHOUT touching the asset's other locations."""
    from inventory.models import AssetLocation

    already = AssetLocation.objects.filter(
        asset=asset, room=room, is_current=True
    ).exists()
    if not already:
        AssetLocation.objects.create(
            asset=asset, room=room, room_unit=None, area="", is_current=True
        )
    _sync_asset_legacy_fields(asset)


def _asset_picker_list():
    """Assets for the picker in Add Room / Edit Room."""
    from inventory.models import HotelAsset

    return [
        {
            "id": a.id,
            "name": a.name,
            "category": a.asset_category.name if a.asset_category else "",
        }
        for a in HotelAsset.objects.select_related("asset_category").order_by("name")
    ]


# ──────────────────────────────────────────────────────────────
# ADD ROOM PAGE
# ──────────────────────────────────────────────────────────────

@login_required
@never_cache
def add_room_page(request):
    from pms.models import Property

    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return redirect("hotel_login")

    hotel_obj = get_object_or_404(Hotel, id=hotel_id)
    amenities_qs = Property.objects.all()

    return render(request, "hotel-setup/add_room.html", {
        "hotel": hotel_obj,
        "amenities": amenities_qs,
        "amenities_json": json.dumps(list(amenities_qs.values("id", "name"))),
        "all_assets_json": json.dumps(_asset_picker_list()),
    })


# ──────────────────────────────────────────────────────────────
# VIEW ROOMS PAGE
# ──────────────────────────────────────────────────────────────

@login_required
@never_cache
def view_rooms_page(request):
    from pms.models import Room, Property
    from inventory.models import AssetLocation

    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return redirect("hotel_login")

    hotel_obj = get_object_or_404(Hotel, id=hotel_id)

    rooms = (
        Room.objects.filter(is_active=True)
        .prefetch_related("images", "amenities")
        .order_by("-id")
    )

    def price_tier(price):
        try:
            p = float(price)
        except (TypeError, ValueError):
            p = 0
        if p >= 2500:
            return "Luxury"
        if p >= 1500:
            return "Premium"
        return "Standard"

    rooms_data = []
    for r in rooms:
        primary_image = r.images.filter(is_primary=True).first() or r.images.first()
        display_type = (
            r.custom_room_type
            if r.room_type == "Custom" and r.custom_room_type
            else r.room_type
        )

        # Assets currently linked to this room (distinct, in case of duplicate rows)
        asset_ids = list(
            AssetLocation.objects.filter(room=r, is_current=True)
            .values_list("asset_id", flat=True)
            .distinct()
        )

        rooms_data.append({
            "id":             r.id,
            "room_type":      r.room_type,
            "display_type":   display_type,
            "description":    r.description or "",
            "units":          r.units.count(),
            "price":          str(r.base_price),
            "overstay_price": str(r.overstay_price),
            "max_adults":     r.max_adults,
            "max_children":   r.max_children,
            "is_active":      r.is_active,
            "tier":           price_tier(r.base_price),
            "image_url":      primary_image.image.url if primary_image else None,
            "amenity_ids":    list(r.amenities.values_list("id", flat=True)),
            "asset_ids":      asset_ids,
            "features":       r.features or [],
        })

    return render(request, "hotel-setup/view_rooms.html", {
        "hotel":           hotel_obj,
        "rooms":           rooms_data,
        "rooms_json":      json.dumps(rooms_data),
        "amenities":       Property.objects.all(),
        "all_assets_json": json.dumps(_asset_picker_list()),
    })


# ──────────────────────────────────────────────────────────────
# EDIT ROOM
# ──────────────────────────────────────────────────────────────

@require_POST
@login_required
def edit_room_view(request, room_id):
    """Handles the 'Save Changes' submit from the Edit Room modal."""
    from pms.models import Room, RoomImage, RoomUnit, Property
    from inventory.models import HotelAsset, AssetLocation

    try:
        with transaction.atomic():
            room = get_object_or_404(Room, id=room_id, is_active=True)

            # ── Simple text/number fields ──
            room_type_name = request.POST.get("room_type_name", "").strip()
            if room_type_name:
                if room.room_type == "Custom":
                    room.custom_room_type = room_type_name
                else:
                    room.room_type = room_type_name

            base_price = request.POST.get("base_price")
            max_adults = request.POST.get("max_adults")
            max_children = request.POST.get("max_children")
            overstay_price = request.POST.get("overstay_price")
            description = request.POST.get("description")

            if base_price not in (None, ""):
                room.base_price = base_price
            if max_adults not in (None, ""):
                room.max_adults = max_adults
            if max_children not in (None, ""):
                room.max_children = max_children
            if overstay_price not in (None, ""):
                room.overstay_price = overstay_price
            if description is not None:
                room.description = description

            # ── Amenities / features ──
            amenity_ids = request.POST.getlist("amenities")
            room.amenities.set(Property.objects.filter(id__in=amenity_ids))
            features = request.POST.getlist("features")
            room.features = [str(f).strip() for f in features if str(f).strip()]

            room.save()

            # ── Assets ──
            asset_ids_int = [
                int(a) for a in request.POST.getlist("asset_ids") if str(a).isdigit()
            ]

            # 1) Unlink assets that were on THIS room but are no longer selected.
            #    Only this room's rows are deactivated; the asset's locations in
            #    other rooms and areas stay untouched.
            removed_qs = AssetLocation.objects.filter(
                room=room, is_current=True
            ).exclude(asset_id__in=asset_ids_int)
            removed_asset_ids = list(removed_qs.values_list("asset_id", flat=True).distinct())
            removed_qs.update(is_current=False)

            for asset in HotelAsset.objects.filter(id__in=removed_asset_ids):
                _sync_asset_legacy_fields(asset)

            # 2) Link selected assets: adds this room, keeps their other locations.
            for asset in HotelAsset.objects.filter(id__in=asset_ids_int):
                _link_asset_to_room(asset, room)

            # ── Total units: grow or shrink the RoomUnit set to match ──
            total_units_raw = request.POST.get("total_units")
            if total_units_raw:
                total_units = int(total_units_raw)
                current_units = list(room.units.order_by("id"))

                if total_units > len(current_units):
                    prefix_map = {"Single": "S", "Double": "D", "Deluxe": "DL", "Suite": "SU"}
                    prefix = prefix_map.get(
                        room.room_type,
                        (room.custom_room_type[:2].upper() if room.custom_room_type else "CR"),
                    )
                    existing_numbers = set(RoomUnit.objects.values_list("room_number", flat=True))
                    new_units, counter = [], 1
                    while len(new_units) < (total_units - len(current_units)):
                        number = f"{prefix}{counter}"
                        if number not in existing_numbers:
                            new_units.append(RoomUnit(room=room, room_number=number))
                            existing_numbers.add(number)
                        counter += 1
                    RoomUnit.objects.bulk_create(new_units)

                elif total_units < len(current_units):
                    # Remove the newest units first
                    to_remove = current_units[total_units:]
                    RoomUnit.objects.filter(id__in=[u.id for u in to_remove]).delete()

            # ── Replace the primary image if a new one was uploaded ──
            if request.FILES.get("image"):
                RoomImage.objects.filter(room=room, is_primary=True).delete()
                RoomImage.objects.create(room=room, image=request.FILES["image"], is_primary=True)

        return JsonResponse({"success": True})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)





@require_http_methods(["DELETE", "POST"])
@login_required
def delete_room_view(request, room_id):
    from pms.models import Room, Booking

    room = get_object_or_404(Room, id=room_id)

    # Keep the room if it has a confirmed or checked-in booking.
    has_bookings = Booking.objects.filter(
        room=room,
        status__in=["confirmed", "checked_in"],
    ).exists()

    if has_bookings:
        return JsonResponse(
            {
                "success": False,
                "error": "Cannot delete a room with active or upcoming bookings.",
            },
            status=400,
        )

    # Permanent deletion: related units and images are deleted if their
    # model foreign keys use on_delete=models.CASCADE.
    room.delete()

    return JsonResponse({"success": True})

from pms.models import Property

@require_POST
@login_required
def add_room_amenity(request):
    """Create a new room amenity (pms.Property) for the current tenant,
    used by the 'Add Custom Amenity' button in the Add Room wizard."""
    try:
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
        name = (data.get("name") or "").strip()

        if not name:
            return JsonResponse({"error": "Amenity name is required."}, status=400)

        amenity, created = Property.objects.get_or_create(name=name)
        if not created:
            return JsonResponse({"error": "An amenity with this name already exists."}, status=400)

        return JsonResponse({"id": amenity.id, "name": amenity.name, "created": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from accounts.models import Hotel, SubscriptionPlan, PlanPayment


def _get_current_hotel(request):
    """
    Resolve the hotel for this request the same way the rest of the
    app does — session hotel_id first, falling back to the logged-in
    staff member's hotel.
    """
    hotel_id = request.session.get("hotel_id")
    if hotel_id:
        hotel = Hotel.objects.filter(id=hotel_id).select_related("subscription_plan").first()
        if hotel:
            return hotel

    staff_id = request.session.get("staff_id")
    if staff_id:
        from accounts.models import Staff
        staff = Staff.objects.filter(id=staff_id).select_related(
            "hotel", "hotel__subscription_plan"
        ).first()
        if staff:
            return staff.hotel

    return None


from django.urls import reverse  # add near the top of the file if not already imported

@login_required
@never_cache
def subscription_page(request):
    """
    Renders the Subscription / Plans page using real Hotel +
    SubscriptionPlan + PlanPayment data.
    """
    hotel = _get_current_hotel(request)
    if not hotel:
        return render(request, "hotel-setup/subscription.html", {
            "current_plan": None,
            "plans": [],
            "error": "No hotel found for this account.",
        })

    active_plan = hotel.subscription_plan  # FK on Hotel -> SubscriptionPlan
    today = timezone.now().date()

    # ── Most recent payment record, for billing-cycle / payment-method display ──
    latest_payment = PlanPayment.objects.filter(
        hotel=hotel
    ).order_by("-created_at").first()

    # ── Days remaining on the current plan/trial, for the header badge ──
    days_remaining = None
    is_trial_period = hotel.is_on_trial and hotel.trial_is_active

    if is_trial_period and hotel.trial_end:
        trial_end_date = (
            hotel.trial_end.date() if hasattr(hotel.trial_end, "date") else hotel.trial_end
        )
        days_remaining = max(0, (trial_end_date - today).days)
    elif hotel.subscription_expiry:
        days_remaining = max(0, (hotel.subscription_expiry - today).days)

    # ── Build "Your Current Plan" block from real fields ──
    if active_plan:
        current_plan = {
            "name": active_plan.name,
            "is_active": hotel.subscription_status == "active" or hotel.trial_is_active,
            "status_label": (
                "Trial" if is_trial_period
                else hotel.get_subscription_status_display()
            ),
            "next_billing_date": (
                hotel.subscription_expiry.strftime("%d %b %Y")
                if hotel.subscription_expiry else
                (hotel.trial_end.strftime("%d %b %Y") if hotel.trial_end else "—")
            ),
            "payment_method": (
                latest_payment.transaction_id if latest_payment and latest_payment.transaction_id
                else "Not on file"
            ),
            "days_remaining": days_remaining,   # NEW
            "is_trial": is_trial_period,        # NEW
            # Pull whatever module/amenity names are attached to this plan
            "modules": list(active_plan.modules.values_list("name", flat=True)),
        }
    else:
        current_plan = {
            "name": "No Active Plan",
            "is_active": False,
            "status_label": hotel.get_subscription_status_display(),
            "next_billing_date": "—",
            "payment_method": "—",
            "days_remaining": None,   # NEW
            "is_trial": False,        # NEW
            "modules": [],
        }

    # ── All sellable plans, ordered cheapest first ──
    plan_qs = SubscriptionPlan.objects.filter(
        is_active=True, is_trial_plan=False
    ).prefetch_related("modules").order_by("price")

    plans = []
    for p in plan_qs:
        plans.append({
            "key": p.id,
            "name": p.name,
            "tagline": p.tagline or "",
            "price": p.price,
            "is_current": bool(active_plan and p.id == active_plan.id),
            # "Most Popular" — pick the middle-priced plan as a simple heuristic,
            # or swap this for a real `is_popular` BooleanField on SubscriptionPlan.
            "is_popular": False,
            "features": list(p.modules.values_list("name", flat=True)),
            "checkout_url": reverse("subscription_checkout", kwargs={"plan_uuid": p.uuid}),  # NEW
        })

    # Mark the middle plan as popular if there are exactly 3+ and none is flagged
    if len(plans) >= 3 and not any(pl["is_popular"] for pl in plans):
        mid = len(plans) // 2
        plans[mid]["is_popular"] = True

    # ── Recent billing history, for the "View Billing History" panel ──
    payment_history = PlanPayment.objects.filter(
        hotel=hotel
    ).select_related("plan").order_by("-created_at")[:10]

    return render(request, "hotel-setup/subscription.html", {
        "hotel": hotel,
        "current_plan": current_plan,
        "plans": plans,
        "payment_history": payment_history,
    })
@login_required
@never_cache
def subscription_checkout(request, plan_uuid):
    """
    Checkout page for a subscription plan, addressed by UUID rather than
    the plan's numeric primary key (avoids exposing/guessing sequential IDs).
    """
    plan = get_object_or_404(SubscriptionPlan, uuid=plan_uuid, is_active=True)
    hotel = _get_current_hotel(request)

    if not hotel:
        messages.error(request, "No hotel found for this account.")
        return redirect("subscription_page")

    already_on_plan = (
        hotel.subscription_plan_id == plan.id
        and hotel.subscription_status == "active"
        and hotel.subscription_expiry
        and hotel.subscription_expiry >= timezone.now().date()
    )
    if already_on_plan:
        messages.info(request, f"You're already subscribed to the {plan.name} plan.")
        return redirect("subscription_page")

    if request.method == "POST":
        payment_method   = request.POST.get("payment_method", "card").strip()
        cardholder_name  = request.POST.get("cardholder_name", "").strip()
        card_number      = request.POST.get("card_number", "").strip()
        expiry           = request.POST.get("expiry", "").strip()
        cvv              = request.POST.get("cvv", "").strip()

        if payment_method == "card" and not (cardholder_name and card_number and expiry and cvv):
            messages.error(request, "Please fill in all card details.")
            return render(request, "hotel-setup/checkout.html", {"hotel": hotel, "plan": plan})

        # ── NOTE ──────────────────────────────────────────────────────────
        # This is where you'd call out to a real payment gateway (Stripe,
        # Razorpay, etc.) and only proceed on a successful charge. For now
        # this mirrors tenant_create_payment(): it records the payment and
        # activates the plan directly.
        # ─────────────────────────────────────────────────────────────────
        with schema_context('public'):
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

            _enable_plan_modules(hotel, plan)

            masked_card = f"**** **** **** {card_number[-4:]}" if card_number else ""
            payment = PlanPayment.objects.create(
                hotel     = hotel,
                plan      = plan,
                amount    = plan.price,
                status    = 'paid',
                due_date  = timezone.now().date() + relativedelta(months=1),
                paid_date = timezone.now().date(),
                notes     = f"payment_method={payment_method}; card={masked_card}",
            )

        try:
            send_mail(
                subject="Subscription Activated",
                message=(
                    f"Hello {hotel.hotel_name},\n\n"
                    f"Your subscription to the {plan.name} plan is now active.\n"
                    f"Amount paid: {plan.price}\n"
                    f"Valid until: {hotel.subscription_expiry.strftime('%d %b %Y')}\n\n"
                    "Regards,\nAdmin Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[hotel.email],
                fail_silently=True,
            )
        except Exception:
            pass

        messages.success(request, f"You're now subscribed to the {plan.name} plan.")
        return redirect("subscription_page")

    return render(request, "hotel-setup/checkout.html", {
        "hotel": hotel,
        "plan": plan,
    })