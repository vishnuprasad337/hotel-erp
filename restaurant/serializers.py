from rest_framework import serializers
from .models import MenuCategory, MenuItem, Table, TableReservation, RestaurantOrder, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    item_name     = serializers.CharField(source='item.name', read_only=True)
    item_price    = serializers.DecimalField(source='item.price', max_digits=10, decimal_places=2, read_only=True)
    item_is_veg   = serializers.BooleanField(source='item.is_veg', read_only=True)
    item_category = serializers.CharField(source='item.category.name', read_only=True)

    class Meta:
        model  = OrderItem
        fields = ['id', 'item_name', 'item_price', 'item_is_veg', 'item_category', 'quantity', 'unit_price', 'subtotal', 'note']


class MenuItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = MenuItem
        fields = ['id', 'name', 'description', 'price', 'tax_percent', 'is_available', 'is_veg', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class MenuCategorySerializer(serializers.ModelSerializer):
    items       = MenuItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model  = MenuCategory
        fields = ['id', 'name', 'order', 'total_items', 'items']


class TableSerializer(serializers.ModelSerializer):
    active_order_count = serializers.SerializerMethodField()

    class Meta:
        model  = Table
        fields = ['id', 'number', 'capacity', 'is_occupied', 'active_order_count']

    def get_active_order_count(self, obj):
        return obj.restaurantorder_set.filter(status__in=['pending', 'preparing']).count()


class TableReservationSerializer(serializers.ModelSerializer):
    table_number   = serializers.IntegerField(source='table.number', read_only=True)
    table_capacity = serializers.IntegerField(source='table.capacity', read_only=True)

    class Meta:
        model  = TableReservation
        fields = ['id', 'guest_name', 'phone', 'guests_count', 'status', 'reservation_time', 'created_at', 'table_number', 'table_capacity']


class RestaurantOrderSerializer(serializers.ModelSerializer):
    items          = OrderItemSerializer(many=True, read_only=True)
    table_number   = serializers.SerializerMethodField()
    room_display   = serializers.SerializerMethodField()
    guest_name     = serializers.SerializerMethodField()
    served_by_name = serializers.SerializerMethodField()
    grand_total    = serializers.SerializerMethodField()
    item_count     = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model  = RestaurantOrder
        fields = ['id', 'order_number', 'order_type', 'status', 'table_number', 'room_display', 'guest_name', 'served_by_name', 'charge_to_room', 'total_amount', 'tax_amount', 'grand_total', 'item_count', 'created_at', 'items']

    def get_table_number(self, obj):
        return obj.table.number if obj.table else None

    def get_room_display(self, obj):
        if obj.booking and obj.booking.room_unit:
            return f"{obj.booking.room_unit.room_number} - {obj.booking.room.room_type}"
        if obj.room:
            return obj.room.room_type
        return None

    def get_guest_name(self, obj):
        if obj.booking and obj.booking.guest:
            return obj.booking.guest.full_name
        if obj.reservation:
            return obj.reservation.guest_name
        return None

    def get_served_by_name(self, obj):
        if obj.served_by:
            return obj.served_by.get_full_name() or obj.served_by.username
        return "Admin"

    def get_grand_total(self, obj):
        return float(obj.total_amount + obj.tax_amount)


class RestaurantFullSerializer(serializers.Serializer):
    stats            = serializers.SerializerMethodField()
    menu_categories  = serializers.SerializerMethodField()
    tables           = serializers.SerializerMethodField()
    reservations     = serializers.SerializerMethodField()
    orders_all       = serializers.SerializerMethodField()
    orders_active    = serializers.SerializerMethodField()
    orders_served    = serializers.SerializerMethodField()
    orders_cancelled = serializers.SerializerMethodField()

    def get_stats(self, obj):
        from django.utils import timezone
        from django.db.models import Sum, Count, Q

        today        = timezone.now().date()
        all_orders   = RestaurantOrder.objects.all()
        today_orders = all_orders.filter(created_at__date=today)

        today_revenue = today_orders.filter(status='served').aggregate(t=Sum('total_amount'))['t'] or 0
        total_revenue = all_orders.filter(status='served').aggregate(t=Sum('total_amount'))['t'] or 0

        counts = all_orders.aggregate(
            pending   = Count('id', filter=Q(status='pending')),
            preparing = Count('id', filter=Q(status='preparing')),
            served    = Count('id', filter=Q(status='served')),
            cancelled = Count('id', filter=Q(status='cancelled')),
        )

        tables_qs            = Table.objects.all()
        menu_items_total     = MenuItem.objects.count()
        menu_items_available = MenuItem.objects.filter(is_available=True).count()
        reservations_today   = TableReservation.objects.filter(reservation_time__date=today).count()

        return {
            "snapshot_date":          today.isoformat(),
            "today_revenue":          float(today_revenue),
            "total_revenue":          float(total_revenue),
            "total_orders":           all_orders.count(),
            "today_orders":           today_orders.count(),
            "pending_orders":         counts['pending'],
            "preparing_orders":       counts['preparing'],
            "served_orders":          counts['served'],
            "cancelled_orders":       counts['cancelled'],
            "active_orders":          counts['pending'] + counts['preparing'],
            "served_today":           today_orders.filter(status='served').count(),
            "tables_total":           tables_qs.count(),
            "tables_occupied":        tables_qs.filter(is_occupied=True).count(),
            "tables_available":       tables_qs.filter(is_occupied=False).count(),
            "reservations_today":     reservations_today,
            "total_reservations":     TableReservation.objects.count(),
            "menu_categories":        MenuCategory.objects.count(),
            "menu_items_total":       menu_items_total,
            "menu_items_available":   menu_items_available,
            "menu_items_unavailable": menu_items_total - menu_items_available,
        }

    def get_menu_categories(self, obj):
        qs = MenuCategory.objects.prefetch_related('items').order_by('order')
        return MenuCategorySerializer(qs, many=True, context=self.context).data

    def get_tables(self, obj):
        qs = Table.objects.all().order_by('number')
        return TableSerializer(qs, many=True).data

    def get_reservations(self, obj):
        qs = TableReservation.objects.select_related('table').order_by('-created_at')
        return TableReservationSerializer(qs, many=True).data

    def _order_qs(self, status=None):
        qs = RestaurantOrder.objects.prefetch_related(
            'items__item__category'
        ).select_related(
            'table', 'room', 'booking__guest',
            'booking__room_unit', 'booking__room',
            'reservation__table', 'served_by',
        ).order_by('-created_at')
        if status:
            qs = qs.filter(status__in=status) if isinstance(status, list) else qs.filter(status=status)
        return qs

    def get_orders_all(self, obj):
        return RestaurantOrderSerializer(self._order_qs(), many=True, context=self.context).data

    def get_orders_active(self, obj):
        return RestaurantOrderSerializer(self._order_qs(['pending', 'preparing']), many=True, context=self.context).data

    def get_orders_served(self, obj):
        return RestaurantOrderSerializer(self._order_qs('served'), many=True, context=self.context).data

    def get_orders_cancelled(self, obj):
        return RestaurantOrderSerializer(self._order_qs('cancelled'), many=True, context=self.context).data