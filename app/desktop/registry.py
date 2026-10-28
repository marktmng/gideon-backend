"""Action Registry defining strictly allowlisted desktop operations."""
from typing import Dict, Any, Callable, Type, Optional
from pydantic import BaseModel
from app.desktop.schemas import (
    DesktopActionType,
    RiskLevel,
    ActionRegistryItem,
    EmptyParams,
    OpenApplicationParams,
    ActivateApplicationParams,
    OpenUrlParams,
    OpenDirectoryParams,
    TypeTextParams,
    PressShortcutParams,
    CaptureScreenshotParams,
    ClickAccessibleElementParams,
)
from app.desktop.adapter import BaseDesktopAdapter


class ActionDefinition:
    """Specification of an allowlisted desktop action."""

    def __init__(
        self,
        action: DesktopActionType,
        name: str,
        description: str,
        param_schema: Type[BaseModel],
        risk_level: RiskLevel,
        default_requires_confirmation: bool,
        handler: Callable[[BaseDesktopAdapter, BaseModel], Dict[str, Any]],
    ):
        self.action = action
        self.name = name
        self.description = description
        self.param_schema = param_schema
        self.risk_level = risk_level
        self.default_requires_confirmation = default_requires_confirmation
        self.handler = handler

    def to_registry_item(self) -> ActionRegistryItem:
        return ActionRegistryItem(
            action=self.action,
            name=self.name,
            description=self.description,
            risk_level=self.risk_level,
            requires_confirmation=self.default_requires_confirmation,
            parameter_schema=self.param_schema.model_json_schema(),
        )


class DesktopActionRegistry:
    """Registry maintaining all supported and validated desktop actions."""

    def __init__(self):
        self._actions: Dict[DesktopActionType, ActionDefinition] = {}
        self._register_default_actions()

    def _register_default_actions(self):
        # 1. Open Application (Stage 1)
        self.register(
            ActionDefinition(
                action=DesktopActionType.open_application,
                name="Open Application",
                description="Launch a trusted allowlisted Windows application by identifier (e.g. 'notepad', 'calculator', 'explorer').",
                param_schema=OpenApplicationParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.open_application(
                    app_name=params.app_name,  # type: ignore
                    args=params.args           # type: ignore
                ),
            )
        )

        # 2. Activate Application (Stage 1)
        self.register(
            ActionDefinition(
                action=DesktopActionType.activate_application,
                name="Activate Application",
                description="Switch focus to an existing application window matching a title or process name.",
                param_schema=ActivateApplicationParams,
                risk_level=RiskLevel.medium,
                default_requires_confirmation=True,
                handler=lambda adapter, params: adapter.activate_application(
                    target=params.target  # type: ignore
                ),
            )
        )

        # 3. Open URL (Stage 1)
        self.register(
            ActionDefinition(
                action=DesktopActionType.open_url,
                name="Open URL",
                description="Open a validated HTTP or HTTPS web address in the default browser.",
                param_schema=OpenUrlParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.open_url(
                    url=params.url  # type: ignore
                ),
            )
        )

        # 4. Open Directory (Stage 1)
        self.register(
            ActionDefinition(
                action=DesktopActionType.open_directory,
                name="Open Directory",
                description="Open an approved local project or user directory in File Explorer.",
                param_schema=OpenDirectoryParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.open_directory(
                    path=params.path  # type: ignore
                ),
            )
        )

        # 5. Open File Explorer (Stage 1)
        self.register(
            ActionDefinition(
                action=DesktopActionType.open_file_explorer,
                name="Open File Explorer",
                description="Launch Windows File Explorer at the default or configured directory.",
                param_schema=EmptyParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.open_file_explorer(),
            )
        )

        # 6. Inspect Active Window (Stage 2)
        self.register(
            ActionDefinition(
                action=DesktopActionType.inspect_active_window,
                name="Inspect Active Window",
                description="Inspect the current foreground window title, process ID, and security classifications.",
                param_schema=EmptyParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.inspect_active_window().model_dump(),
            )
        )

        # 7. Type Text (Stage 2)
        self.register(
            ActionDefinition(
                action=DesktopActionType.type_text,
                name="Type Text",
                description="Type explicitly approved text into a confirmed foreground target window.",
                param_schema=TypeTextParams,
                risk_level=RiskLevel.medium,
                default_requires_confirmation=True,
                handler=lambda adapter, params: adapter.type_text(
                    target_window=params.target_window,  # type: ignore
                    text=params.text                     # type: ignore
                ),
            )
        )

        # 8. Press Shortcut (Stage 2)
        self.register(
            ActionDefinition(
                action=DesktopActionType.press_shortcut,
                name="Press Shortcut",
                description="Press an allowlisted keyboard combination in a confirmed foreground window.",
                param_schema=PressShortcutParams,
                risk_level=RiskLevel.medium,
                default_requires_confirmation=True,
                handler=lambda adapter, params: adapter.press_shortcut(
                    target_window=params.target_window,  # type: ignore
                    shortcut=params.shortcut             # type: ignore
                ),
            )
        )

        # 9. Capture Screenshot (Stage 3)
        self.register(
            ActionDefinition(
                action=DesktopActionType.capture_screenshot,
                name="Capture Screenshot",
                description="Capture a desktop or window screenshot stored 100% locally. Never transmitted externally.",
                param_schema=CaptureScreenshotParams,
                risk_level=RiskLevel.low,
                default_requires_confirmation=False,
                handler=lambda adapter, params: adapter.capture_screenshot(
                    local_only=getattr(params, "local_only", True),
                    target=getattr(params, "target", None)
                ),
            )
        )

        # 10. Click Accessible Element (Stage 4)
        self.register(
            ActionDefinition(
                action=DesktopActionType.click_accessible_element,
                name="Click Accessible Element",
                description="Semantically locate and interact with an accessible UI element.",
                param_schema=ClickAccessibleElementParams,
                risk_level=RiskLevel.medium,
                default_requires_confirmation=True,
                handler=lambda adapter, params: adapter.click_accessible_element(
                    target_window=params.target_window,               # type: ignore
                    element_name=params.element_name,                 # type: ignore
                    control_type=getattr(params, "control_type", None)
                ),
            )
        )

    def register(self, action_def: ActionDefinition):
        self._actions[action_def.action] = action_def

    def get(self, action: DesktopActionType) -> Optional[ActionDefinition]:
        return self._actions.get(action)

    def list_actions(self) -> Dict[DesktopActionType, ActionDefinition]:
        return self._actions
