from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .serializers import (
    RestaurantFullSerializer,
    RestaurantOrderSerializer,
    MenuCategorySerializer,
    TableSerializer,
    TableReservationSerializer,
)

from .models import (
    RestaurantOrder,
    MenuCategory,
    Table,
    TableReservation,
    MenuItem,
)


class RestaurantFullAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = RestaurantFullSerializer(
            {},
            context={'request': request}
        )
        return Response(serializer.data)


class RestaurantOrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        qs = RestaurantOrder.objects.prefetch_related(
            'items__item__category'
        ).select_related(
            'table',
            'room',
            'booking__guest',
            'booking__room_unit',
            'booking__room',
            'reservation__table',
            'served_by',
        ).order_by('-created_at')

        status = request.query_params.get('status')
        order_type = request.query_params.get('order_type')
        date = request.query_params.get('date')
        table_num = request.query_params.get('table')

        if status:
            qs = qs.filter(status=status)

        if order_type:
            qs = qs.filter(order_type=order_type)

        if date:
            qs = qs.filter(created_at__date=date)

        if table_num:
            qs = qs.filter(table__number=table_num)

        serializer = RestaurantOrderSerializer(
            qs,
            many=True,
            context={'request': request}
        )

        return Response({
            "count": qs.count(),
            "orders": serializer.data
        })


class RestaurantOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:
            order = RestaurantOrder.objects.prefetch_related(
                'items__item__category'
            ).select_related(
                'table',
                'room',
                'booking__guest',
                'booking__room_unit',
                'booking__room',
                'reservation__table',
                'served_by',
            ).get(pk=pk)

        except RestaurantOrder.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=404
            )

        serializer = RestaurantOrderSerializer(
            order,
            context={'request': request}
        )

        return Response(serializer.data)


class RestaurantMenuAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        qs = MenuCategory.objects.prefetch_related(
            'items'
        ).order_by('order')

        serializer = MenuCategorySerializer(
            qs,
            many=True,
            context={'request': request}
        )

        return Response({
            "count": qs.count(),
            "categories": serializer.data
        })


class RestaurantTableAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        qs = Table.objects.all().order_by('number')

        occupied = request.query_params.get(
            'occupied',
            ''
        ).lower()

        if occupied == 'true':
            qs = qs.filter(is_occupied=True)

        elif occupied == 'false':
            qs = qs.filter(is_occupied=False)

        serializer = TableSerializer(qs, many=True)

        return Response({
            "count": qs.count(),
            "tables": serializer.data
        })


class RestaurantReservationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        qs = TableReservation.objects.select_related(
            'table'
        ).order_by('-created_at')

        status = request.query_params.get('status')
        date = request.query_params.get('date')

        if status:
            qs = qs.filter(status=status)

        if date:
            qs = qs.filter(
                reservation_time__date=date
            )

        serializer = TableReservationSerializer(
            qs,
            many=True
        )

        return Response({
            "count": qs.count(),
            "reservations": serializer.data
        })


class RestaurantStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        from django.db.models import Sum, Count, Q
        from django.utils import timezone

        date_str = request.query_params.get('date')

        if date_str:
            from datetime import date as _date

            try:
                target_date = _date.fromisoformat(date_str)

            except ValueError:
                return Response(
                    {
                        "error": "Invalid date format. Use YYYY-MM-DD"
                    },
                    status=400
                )

        else:
            target_date = timezone.now().date()

        all_orders = RestaurantOrder.objects.all()

        target_orders = all_orders.filter(
            created_at__date=target_date
        )

        tables_qs = Table.objects.all()

        revenue_target = target_orders.filter(
            status='served'
        ).aggregate(
            t=Sum('total_amount')
        )['t'] or 0

        total_revenue = all_orders.filter(
            status='served'
        ).aggregate(
            t=Sum('total_amount')
        )['t'] or 0

        counts = all_orders.aggregate(
            pending=Count(
                'id',
                filter=Q(status='pending')
            ),
            preparing=Count(
                'id',
                filter=Q(status='preparing')
            ),
            served=Count(
                'id',
                filter=Q(status='served')
            ),
            cancelled=Count(
                'id',
                filter=Q(status='cancelled')
            ),
        )

        return Response({
            "date": target_date.isoformat(),
            "revenue_for_date": float(revenue_target),
            "total_revenue_all_time": float(total_revenue),
            "total_orders": all_orders.count(),
            "orders_on_date": target_orders.count(),
            "pending_orders": counts['pending'],
            "preparing_orders": counts['preparing'],
            "active_orders": counts['pending'] + counts['preparing'],
            "served_orders": counts['served'],
            "cancelled_orders": counts['cancelled'],
            "served_on_date": target_orders.filter(
                status='served'
            ).count(),
            "tables_total": tables_qs.count(),
            "tables_occupied": tables_qs.filter(
                is_occupied=True
            ).count(),
            "tables_available": tables_qs.filter(
                is_occupied=False
            ).count(),
            "reservations_on_date": TableReservation.objects.filter(
                reservation_time__date=target_date
            ).count(),
            "menu_items_total": MenuItem.objects.count(),
            "menu_items_available": MenuItem.objects.filter(
                is_available=True
            ).count(),
        })