from rest_framework import serializers

from .models import Store, Tenant, User


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
