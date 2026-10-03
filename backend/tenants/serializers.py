from rest_framework import serializers

from .models import Store, Tenant, TenantSettings, User


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = (
            "id",
            "name",
            "code",
            "phone",
            "address",
            "block_khata_over_limit",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ("id", "tenant", "name", "address", "phone", "is_active")
        read_only_fields = ("id", "tenant")


class UserSerializer(serializers.ModelSerializer):
    """User management serializer. Password is write-only and always hashed."""

    password = serializers.CharField(write_only=True, required=False, min_length=4)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "is_active",
            "tenant",
            "tenant_name",
            "store",
            "store_name",
            "date_joined",
            "last_login",
        )
        read_only_fields = ("id", "tenant", "date_joined", "last_login")

    def validate_store(self, store):
        request = self.context["request"]
        if store is None:
            return store
        user = request.user
        if not user.is_superuser and store.tenant_id != user.tenant_id:
            raise serializers.ValidationError("Store must belong to your tenant.")
        return store

    def validate_role(self, role):
        if role not in dict(User.ROLE_CHOICES):
            raise serializers.ValidationError("Invalid role.")
        return role

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})
        request = self.context["request"]
        if not request.user.is_superuser:
            # Tenant is forced from the requester; never trust client input.
            validated_data["tenant"] = request.user.tenant
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Per-tenant WhatsApp + print config.

    The access token is write-only and masked on read ('****' + last 4).
    Omitting the token (or sending it empty) on PUT keeps the stored one —
    it is never blanked by accident.
    """

    whatsapp_access_token = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )
    whatsapp_access_token_masked = serializers.CharField(
        source="token_masked", read_only=True
    )

    class Meta:
        model = TenantSettings
        fields = (
            "id",
            "whatsapp_mode",
            "whatsapp_phone_number_id",
            "whatsapp_access_token",
            "whatsapp_access_token_masked",
            "whatsapp_test_mode",
            "whatsapp_test_number",
            "default_print_format",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")

    def validate(self, attrs):
        mode = attrs.get(
            "whatsapp_mode",
            self.instance.whatsapp_mode if self.instance else TenantSettings.MODE_DUMMY,
        )
        phone_id = attrs.get(
            "whatsapp_phone_number_id",
            self.instance.whatsapp_phone_number_id if self.instance else "",
        )
        token = attrs.get("whatsapp_access_token") or (
            self.instance.whatsapp_access_token if self.instance else ""
        )
        if mode == TenantSettings.MODE_META and (not phone_id or not token):
            raise serializers.ValidationError(
                "Meta mode needs whatsapp_phone_number_id and whatsapp_access_token. "
                "Send the token once — it is kept afterwards and never shown in full."
            )
        return attrs

    def update(self, instance, validated_data):
        token = validated_data.pop("whatsapp_access_token", None)
        if token:  # empty/absent token keeps the stored one
            instance.whatsapp_access_token = token
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
