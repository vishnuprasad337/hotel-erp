from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import (
    Amenity, Task, ShiftTemplate, Shift, InventoryItem,
    Attendance, LeaveRequest, Payroll, PayrollLineItem,
    EmployeeFinancialAccount, FinalSettlement,
    MessageThread, Message, MessageAttachment,
    MessageReadStatus, Reaction, PinnedMessage, StarredMessage,
    Mention, Poll, PollOption, PollVote, Notification,
)
from .serializers import (
    AmenitySerializer, TaskSerializer, TaskCreateSerializer,
    ShiftTemplateSerializer, ShiftSerializer, InventoryItemSerializer,
    AttendanceSerializer, LeaveRequestSerializer,
    PayrollSerializer, PayrollLineItemSerializer,
    EmployeeFinancialAccountSerializer, FinalSettlementSerializer,
    MessageThreadSerializer, MessageSerializer, MessageAttachmentSerializer,
    MessageReadStatusSerializer, ReactionSerializer,
    PinnedMessageSerializer, StarredMessageSerializer,
    MentionSerializer, PollSerializer, PollVoteSerializer,
    NotificationSerializer,
)


class AmenityListAPIView(APIView):
    def get(self, request):
        data = AmenitySerializer(Amenity.objects.all(), many=True).data
        return Response(data)

    def post(self, request):
        s = AmenitySerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class AmenityDetailAPIView(APIView):
    def get(self, request, pk):
        obj = get_object_or_404(Amenity, pk=pk)
        return Response(AmenitySerializer(obj).data)

    def put(self, request, pk):
        obj = get_object_or_404(Amenity, pk=pk)
        s = AmenitySerializer(obj, data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(Amenity, pk=pk).delete()
        return Response({"success": True}, status=204)


class TaskListAPIView(APIView):
    def get(self, request):
        tasks = Task.objects.select_related("staff", "room", "room_unit").order_by("-created_at")
        return Response(TaskSerializer(tasks, many=True).data)

    def post(self, request):
        s = TaskCreateSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class TaskDetailAPIView(APIView):
    def get(self, request, pk):
        obj = get_object_or_404(Task, pk=pk)
        return Response(TaskSerializer(obj).data)

    def put(self, request, pk):
        obj = get_object_or_404(Task, pk=pk)
        s = TaskCreateSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(Task, pk=pk).delete()
        return Response({"success": True}, status=204)


class ShiftTemplateListAPIView(APIView):
    def get(self, request):
        return Response(ShiftTemplateSerializer(ShiftTemplate.objects.all(), many=True).data)

    def post(self, request):
        s = ShiftTemplateSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class ShiftTemplateDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(ShiftTemplateSerializer(get_object_or_404(ShiftTemplate, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(ShiftTemplate, pk=pk)
        s = ShiftTemplateSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(ShiftTemplate, pk=pk).delete()
        return Response({"success": True}, status=204)


class ShiftListAPIView(APIView):
    def get(self, request):
        return Response(ShiftSerializer(Shift.objects.select_related("hotel", "department", "staff").all(), many=True).data)

    def post(self, request):
        s = ShiftSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class ShiftDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(ShiftSerializer(get_object_or_404(Shift, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(Shift, pk=pk)
        s = ShiftSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(Shift, pk=pk).delete()
        return Response({"success": True}, status=204)


class InventoryItemListAPIView(APIView):
    def get(self, request):
        return Response(InventoryItemSerializer(InventoryItem.objects.select_related("hotel", "room").all(), many=True).data)

    def post(self, request):
        s = InventoryItemSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class InventoryItemDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(InventoryItemSerializer(get_object_or_404(InventoryItem, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(InventoryItem, pk=pk)
        s = InventoryItemSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(InventoryItem, pk=pk).delete()
        return Response({"success": True}, status=204)


class AttendanceListAPIView(APIView):
    def get(self, request):
        return Response(AttendanceSerializer(Attendance.objects.select_related("staff", "hotel").all(), many=True).data)

    def post(self, request):
        s = AttendanceSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class AttendanceDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(AttendanceSerializer(get_object_or_404(Attendance, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(Attendance, pk=pk)
        s = AttendanceSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class LeaveRequestListAPIView(APIView):
    def get(self, request):
        return Response(LeaveRequestSerializer(LeaveRequest.objects.select_related("staff").all(), many=True).data)

    def post(self, request):
        s = LeaveRequestSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class LeaveRequestDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(LeaveRequestSerializer(get_object_or_404(LeaveRequest, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(LeaveRequest, pk=pk)
        s = LeaveRequestSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class PayrollListAPIView(APIView):
    def get(self, request):
        return Response(PayrollSerializer(Payroll.objects.prefetch_related("line_items").all(), many=True).data)

    def post(self, request):
        s = PayrollSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class PayrollDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(PayrollSerializer(get_object_or_404(Payroll, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(Payroll, pk=pk)
        s = PayrollSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class EmployeeFinancialAccountAPIView(APIView):
    def get(self, request, staff_id):
        obj = get_object_or_404(EmployeeFinancialAccount, staff_id=staff_id)
        return Response(EmployeeFinancialAccountSerializer(obj).data)

    def put(self, request, staff_id):
        obj = get_object_or_404(EmployeeFinancialAccount, staff_id=staff_id)
        s = EmployeeFinancialAccountSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class FinalSettlementListAPIView(APIView):
    def get(self, request):
        return Response(FinalSettlementSerializer(FinalSettlement.objects.select_related("staff").all(), many=True).data)

    def post(self, request):
        s = FinalSettlementSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class FinalSettlementDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(FinalSettlementSerializer(get_object_or_404(FinalSettlement, pk=pk)).data)


class MessageThreadListAPIView(APIView):
    def get(self, request):
        threads = MessageThread.objects.prefetch_related("memberships").order_by("-updated_at")
        return Response(MessageThreadSerializer(threads, many=True).data)

    def post(self, request):
        s = MessageThreadSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class MessageThreadDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(MessageThreadSerializer(get_object_or_404(MessageThread, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(MessageThread, pk=pk)
        s = MessageThreadSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(MessageThread, pk=pk).delete()
        return Response({"success": True}, status=204)


class MessageListAPIView(APIView):
    def get(self, request, thread_id):
        messages = Message.objects.prefetch_related("attachments").filter(
            thread_id=thread_id, is_deleted=False
        ).order_by("created_at")
        return Response(MessageSerializer(messages, many=True).data)

    def post(self, request, thread_id):
        data = request.data.copy()
        data["thread"] = thread_id
        s = MessageSerializer(data=data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class MessageDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(MessageSerializer(get_object_or_404(Message, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(Message, pk=pk)
        s = MessageSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        obj = get_object_or_404(Message, pk=pk)
        obj.soft_delete()
        return Response({"success": True})


class ReactionAPIView(APIView):
    def post(self, request):
        s = ReactionSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)

    def delete(self, request):
        obj = get_object_or_404(
            Reaction,
            message_id=request.data.get("message"),
            user_id=request.data.get("user"),
            emoji=request.data.get("emoji"),
        )
        obj.delete()
        return Response({"success": True}, status=204)


class PinnedMessageListAPIView(APIView):
    def get(self, request, thread_id):
        pins = PinnedMessage.objects.filter(thread_id=thread_id).select_related("message", "pinned_by")
        return Response(PinnedMessageSerializer(pins, many=True).data)

    def post(self, request):
        s = PinnedMessageSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class StarredMessageListAPIView(APIView):
    def get(self, request):
        stars = StarredMessage.objects.filter(user=request.user).select_related("message")
        return Response(StarredMessageSerializer(stars, many=True).data)

    def post(self, request):
        s = StarredMessageSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class PollAPIView(APIView):
    def get(self, request, pk):
        poll = get_object_or_404(Poll.objects.prefetch_related("options"), pk=pk)
        return Response(PollSerializer(poll).data)

    def post(self, request):
        s = PollSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class PollVoteAPIView(APIView):
    def post(self, request):
        s = PollVoteSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class NotificationListAPIView(APIView):
    def get(self, request):
        notifs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
        return Response(NotificationSerializer(notifs, many=True).data)


class NotificationMarkReadAPIView(APIView):
    def post(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notif.mark_read()
        return Response({"success": True})