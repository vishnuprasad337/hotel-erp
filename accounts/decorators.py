from functools import wraps
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache

def staff_login_required(view_func):
    @wraps(view_func)
    @never_cache
    def wrapper(request, *args, **kwargs):
        staff_id = request.session.get("staff_id")
        if not staff_id:
            return redirect("staff_login")
        return view_func(request, *args, **kwargs)
    return wrapper