from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CatalogValidation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CATALOG_VALIDATION_UNSPECIFIED: _ClassVar[CatalogValidation]
    CATALOG_VALIDATION_PENDING: _ClassVar[CatalogValidation]

class CheckoutReadiness(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHECKOUT_READINESS_UNSPECIFIED: _ClassVar[CheckoutReadiness]
    CHECKOUT_BLOCKED: _ClassVar[CheckoutReadiness]
CATALOG_VALIDATION_UNSPECIFIED: CatalogValidation
CATALOG_VALIDATION_PENDING: CatalogValidation
CHECKOUT_READINESS_UNSPECIFIED: CheckoutReadiness
CHECKOUT_BLOCKED: CheckoutReadiness

class GetDesignDraftRequest(_message.Message):
    __slots__ = ("design_id",)
    DESIGN_ID_FIELD_NUMBER: _ClassVar[int]
    design_id: str
    def __init__(self, design_id: _Optional[str] = ...) -> None: ...

class DesignApplication(_message.Message):
    __slots__ = ("id", "zone_id", "zone_size_id", "print_version_id", "file_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_SIZE_ID_FIELD_NUMBER: _ClassVar[int]
    PRINT_VERSION_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    zone_id: str
    zone_size_id: str
    print_version_id: str
    file_id: str
    def __init__(self, id: _Optional[str] = ..., zone_id: _Optional[str] = ..., zone_size_id: _Optional[str] = ..., print_version_id: _Optional[str] = ..., file_id: _Optional[str] = ...) -> None: ...

class DesignDraft(_message.Message):
    __slots__ = ("id", "owner_id", "variant_id", "template_id", "state", "version", "front_preview_id", "back_preview_id", "applications")
    ID_FIELD_NUMBER: _ClassVar[int]
    OWNER_ID_FIELD_NUMBER: _ClassVar[int]
    VARIANT_ID_FIELD_NUMBER: _ClassVar[int]
    TEMPLATE_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    FRONT_PREVIEW_ID_FIELD_NUMBER: _ClassVar[int]
    BACK_PREVIEW_ID_FIELD_NUMBER: _ClassVar[int]
    APPLICATIONS_FIELD_NUMBER: _ClassVar[int]
    id: str
    owner_id: str
    variant_id: str
    template_id: str
    state: str
    version: int
    front_preview_id: str
    back_preview_id: str
    applications: _containers.RepeatedCompositeFieldContainer[DesignApplication]
    def __init__(self, id: _Optional[str] = ..., owner_id: _Optional[str] = ..., variant_id: _Optional[str] = ..., template_id: _Optional[str] = ..., state: _Optional[str] = ..., version: _Optional[int] = ..., front_preview_id: _Optional[str] = ..., back_preview_id: _Optional[str] = ..., applications: _Optional[_Iterable[_Union[DesignApplication, _Mapping]]] = ...) -> None: ...

class GetDesignDraftResponse(_message.Message):
    __slots__ = ("design", "etag", "catalog_validation", "checkout_readiness", "diagnostic_only")
    DESIGN_FIELD_NUMBER: _ClassVar[int]
    ETAG_FIELD_NUMBER: _ClassVar[int]
    CATALOG_VALIDATION_FIELD_NUMBER: _ClassVar[int]
    CHECKOUT_READINESS_FIELD_NUMBER: _ClassVar[int]
    DIAGNOSTIC_ONLY_FIELD_NUMBER: _ClassVar[int]
    design: DesignDraft
    etag: str
    catalog_validation: CatalogValidation
    checkout_readiness: CheckoutReadiness
    diagnostic_only: bool
    def __init__(self, design: _Optional[_Union[DesignDraft, _Mapping]] = ..., etag: _Optional[str] = ..., catalog_validation: _Optional[_Union[CatalogValidation, str]] = ..., checkout_readiness: _Optional[_Union[CheckoutReadiness, str]] = ..., diagnostic_only: _Optional[bool] = ...) -> None: ...
