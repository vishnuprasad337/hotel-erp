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




@login_required
def superuser_dashboard(request):

    if not request.user.is_superuser:
        return redirect("admin_login")

    
    connection.set_schema_to_public()

    hotels = Hotel.objects.all().order_by("-id")

    total_hotels = hotels.count()
    active_hotels = hotels.filter(is_approved=True).count()
    pending_hotels = hotels.filter(is_approved=False).count()

    pending_hotel_list = hotels.filter(is_approved=False)

    amenities = Amenity.objects.all()

    return render(request, "admin/dashboard.html", {
        "hotels": hotels,
        "total_hotels": total_hotels,
        "active_hotels": active_hotels,
        "pending_hotels": pending_hotels,
        "pending_hotel_list": pending_hotel_list,
        "amenities": amenities,
    })

@login_required
def approve_hotel(request, id):
    if not request.user.is_superuser:
        return redirect("admin_login")

    hotel = get_object_or_404(Hotel, id=id)
    hotel.is_approved = True
    hotel.save()

    return redirect("superuser_dashboard")


@login_required
def reject_hotel(request, id):
    if not request.user.is_superuser:
        return redirect("admin_login")

    hotel = get_object_or_404(Hotel, id=id)
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


##----------------------Hotel Authentication----------------------
from django.shortcuts import render, redirect
from django.conf import settings
from django.db import transaction

from .forms import HotelForm
from customers.models import Domain,Client


from django.shortcuts import render, redirect
from django.core.management import call_command
from django.utils.text import slugify
from django_tenants.utils import schema_context

from .forms import HotelForm

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
                        password = form.cleaned_data.get("password")  # add to form

                        user = User.objects.create_user(
                            username=email,
                            email=email,
                            password=password,
                            hotel=hotel,
                        )

                return redirect(f"http://{domain.domain}{settings.PORT}")

            except Exception as e:
                print("ERROR:", e)
                form.add_error(None, "Something went wrong")

    return render(request, "register.html", {
        "tenant_form": HotelForm()
    })
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
            # Validation
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

        
        current_tenant = connection.tenant

       
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

        return redirect("dashboard")

    return render(request, "login.html", {
        "error": error,
        "success": success_msg
    })
def amenities_page(request):
    amenities = Amenity.objects.all()
    return render(request, "amenities.html", {"amenities": amenities})










from django.db import connection

from django_tenants.utils import schema_context, get_tenant_model




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
        data = json.loads(request.body)

        name = data.get("name")
        description = data.get("description", "")
        amenity_type = data.get("amenity_type", "default")

        
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)

        if amenity_type not in ["default", "premium"]:
            return JsonResponse({"error": "Invalid amenity_type"}, status=400)

        
        amenity, created = Amenity.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "amenity_type": amenity_type
            }
        )

        if not created:
            amenity.description = description
            amenity.amenity_type = amenity_type
            amenity.save()

        return JsonResponse({
            "id": amenity.id,
            "name": amenity.name,
            "description": amenity.description,
            "amenity_type": amenity.amenity_type,
            "created": created
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def get_amenities(request):
    try:
        default_amenities = Amenity.objects.filter(
            amenity_type="default"
        ).values("id", "name", "description")

        premium_amenities = Amenity.objects.filter(
            amenity_type="premium"
        ).values("id", "name", "description")

        return JsonResponse({
            "default": list(default_amenities),
            "premium": list(premium_amenities)
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
from django.views.decorators.http import require_http_methods
@require_http_methods(["DELETE"])
def delete_amenity(request, amenity_id):
    try:
        amenity = get_object_or_404(Amenity, id=amenity_id)

        amenity.delete()

        return JsonResponse({
            "message": "Amenity deleted successfully",
            "id": amenity_id
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

from pms.models import Room, RoomUnit

def dashboard(request):
    current_tenant = connection.tenant

    with schema_context('public'):
        hotel = Hotel.objects.get(schema_name=current_tenant.schema_name)

    modules = HotelModule.objects.select_related('module')
    amenities = [m.module for m in modules]

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
    result = []
    for dept in Department.objects.all():
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
        role = data.get("role", "Staff")

        if not all([name, email, password]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        tenant = connection.tenant

        with schema_context('public'):
            try:
                hotel = Hotel.objects.get(schema_name=tenant.schema_name)
            except Hotel.DoesNotExist:
                return JsonResponse({"error": "Hotel not found"}, status=404)

        with schema_context(tenant.schema_name):
            if User.objects.filter(username=email).exists():
                return JsonResponse({"error": "User already exists"}, status=400)

        department = None
        if department_id:
            with schema_context(tenant.schema_name):
                department = Department.objects.filter(id=int(department_id)).first()
                if not department:
                    return JsonResponse({"error": "Department not found"}, status=400)

        with schema_context(tenant.schema_name):
            user = User.objects.create_user(
                username=email,
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

                staff_list.append({
                    "id": s.id,
                    "employee_id": s.employee_id,
                    "name": s.name,
                    "email": s.user.email if s.user else "",
                    "phone": s.phone or "",
                    "department": {
                        "id": dept.id if dept else None,
                        "name": dept.name if dept else None,
                        "permissions": dept_permissions_map.get(dept.id, []) if dept else []
                    },
                    "salary": str(s.salary),
                    "photo": s.photo.url if s.photo else None,
                    "is_active": s.is_active,
                })

        return JsonResponse({
            "success": True,
            "count": len(staff_list),
            "staffs": staff_list
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
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

        # Also delete the associated user
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

        
        user = authenticate(request, username=email, password=password)

        if user is None:
            return render(request, "staff_login.html", {
                "error": "Invalid credentials"
            })

       
        if not user.is_active:
            return render(request, "staff_login.html", {
                "error": "Account disabled"
            })

        current_tenant = connection.tenant

        
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
        }

        return redirect(redirect_map.get(dept, "staff_dashboard"))

    return render(request, "staff_login.html")