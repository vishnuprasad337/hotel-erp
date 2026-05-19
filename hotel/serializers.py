from rest_framework import serializers
from .models import (
    Amenity, Task, ShiftTemplate, Shift, InventoryItem,
    Attendance, LeaveRequest, Payroll, PayrollLineItem,
    EmployeeFinancialAccount, FinalSettlement,
    MessageThread, ThreadParticipant, Message, MessageAttachment,
    MessageReadStatus, Reaction, PinnedMessage, StarredMessage,
    Mention, Poll, PollOption, PollVote, Notification,
)


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Amenity
        fields = ["id", "name", "description", "amenity_type"]


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Task
        fields = ["id", "staff", "room", "room_unit", "title", "description", "status", "created_at"]


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Task
        fields = ["id", "staff", "room", "room_unit", "title", "description", "status"]


class ShiftTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ShiftTemplate
        fields = ["id", "hotel", "shift_name", "start_time", "end_time", "color", "is_active"]


class ShiftSerializer(serializers.ModelSerializer):
    start_time = serializers.SerializerMethodField()
    end_time   = serializers.SerializerMethodField()

    class Meta:
        model  = Shift
        fields = [
            "id", "hotel", "department", "staff", "shift", "date",
            "custom_name", "custom_start", "custom_end", "custom_color",
            "start_time", "end_time",
        ]

    def get_start_time(self, obj):
        return str(obj.get_start_time())

    def get_end_time(self, obj):
        return str(obj.get_end_time())


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InventoryItem
        fields = [
            "id", "hotel", "room", "name", "category", "quantity",
            "unit", "reorder_level", "description", "assigned_by",
            "assigned_date", "updated_at", "updated_by",
        ]


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Attendance
        fields = [
            "id", "staff", "hotel", "date", "check_in", "check_out",
            "status", "overtime_hours", "is_corrected", "correction_note", "created_at",
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LeaveRequest
        fields = [
            "id", "staff", "from_date", "to_date", "reason",
            "status", "applied_at", "action_by", "action_at",
        ]


class PayrollLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PayrollLineItem
        fields = [
            "id", "line_type", "source", "label", "amount",
            "pct", "pct_base", "is_auto", "note", "order",
        ]


class PayrollSerializer(serializers.ModelSerializer):
    line_items = PayrollLineItemSerializer(many=True, read_only=True)

    class Meta:
        model  = Payroll
        fields = [
            "id", "staff", "hotel", "month", "year",
            "basic_salary", "overtime_amount", "bonus", "incentive",
            "deductions", "pf_amount", "esi_amount", "tax_deduction", "loan_deduction",
            "net_salary", "custom_earnings", "custom_deductions", "notes",
            "generated_at", "paid_status", "paid_at", "paid_by",
            "line_items",
        ]


class EmployeeFinancialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model  = EmployeeFinancialAccount
        fields = [
            "id", "staff", "pf_balance", "esi_balance",
            "loan_balance", "advance_balance", "gratuity_balance", "updated_at",
        ]


class FinalSettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FinalSettlement
        fields = [
            "id", "staff", "last_working_day", "pending_salary",
            "leave_encashment", "gratuity", "pf_payable",
            "total_deductions", "final_amount", "settled_at",
        ]


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MessageAttachment
        fields = ["id", "file", "file_name", "file_size", "file_type", "uploaded_at"]


class MessageSerializer(serializers.ModelSerializer):
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model  = Message
        fields = [
            "id", "thread", "sender", "body", "priority",
            "reply_to", "forwarded_from", "is_edited", "is_deleted",
            "is_system_msg", "created_at", "updated_at", "attachments",
        ]


class ThreadParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ThreadParticipant
        fields = ["id", "user", "is_admin", "is_muted", "is_pinned_chat", "last_read_at", "joined_at"]


class MessageThreadSerializer(serializers.ModelSerializer):
    memberships = ThreadParticipantSerializer(many=True, read_only=True)

    class Meta:
        model  = MessageThread
        fields = [
            "id", "hotel", "thread_type", "name", "description", "avatar",
            "department", "is_archived", "is_locked", "max_members",
            "created_by", "created_at", "updated_at", "memberships",
        ]


class MessageReadStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MessageReadStatus
        fields = ["id", "message", "user", "read_at"]


class ReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Reaction
        fields = ["id", "message", "user", "emoji"]


class PinnedMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PinnedMessage
        fields = ["id", "thread", "message", "pinned_by", "pinned_at"]


class StarredMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StarredMessage
        fields = ["id", "user", "message", "starred_at"]


class MentionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Mention
        fields = ["id", "message", "mentioned_user", "is_all"]


class PollOptionSerializer(serializers.ModelSerializer):
    vote_count = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model  = PollOption
        fields = ["id", "text", "order", "vote_count", "percentage"]

    def get_vote_count(self, obj):
        return obj.vote_count()

    def get_percentage(self, obj):
        return obj.percentage()


class PollSerializer(serializers.ModelSerializer):
    options     = PollOptionSerializer(many=True, read_only=True)
    total_votes = serializers.SerializerMethodField()
    is_open     = serializers.SerializerMethodField()

    class Meta:
        model  = Poll
        fields = [
            "id", "message", "question", "is_anonymous",
            "allow_multi", "closes_at", "created_at",
            "total_votes", "is_open", "options",
        ]

    def get_total_votes(self, obj):
        return obj.total_votes

    def get_is_open(self, obj):
        return obj.is_open


class PollVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PollVote
        fields = ["id", "option", "user", "voted_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = [
            "id", "recipient", "notif_type", "title", "body",
            "thread", "message", "is_read", "created_at",
        ]