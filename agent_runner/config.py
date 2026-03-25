from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_runner.models import AppConfig


DEFAULT_MODEL_PROVIDER = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_LMSTUDIO_MODEL = "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive"
DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_APPIUM_URL = "http://127.0.0.1:4723"
DEFAULT_DEVICE_SERIAL = "emulator-5554"
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_SKILLS_DIR = Path("skills/apps")
DEFAULT_SYSTEM_SKILL_FILE = Path("skills/system/android_navigation/SKILL.md")


@dataclass(slots=True)
class RuntimeConfig:
    appium_url: str
    device_serial: str
    model_provider: str
    model_name: str
    gemini_api_key: str | None
    gemini_model: str
    lmstudio_api_key: str | None
    lmstudio_model: str
    lmstudio_base_url: str
    runs_dir: Path
    skills_dir: Path
    system_skill_file: Path
    adb_path: str
    android_sdk_root: str


def load_runtime_config() -> RuntimeConfig:
    _load_local_env_files()
    model_provider = os.environ.get("AGENT_RUNNER_MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER).strip().casefold()
    if model_provider not in {"gemini", "lmstudio"}:
        model_provider = DEFAULT_MODEL_PROVIDER
    gemini_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    lmstudio_model = os.environ.get("LMSTUDIO_MODEL", DEFAULT_LMSTUDIO_MODEL)
    model_name = os.environ.get("AGENT_RUNNER_MODEL_NAME") or (
        lmstudio_model if model_provider == "lmstudio" else gemini_model
    )
    android_sdk_root = os.environ.get("ANDROID_SDK_ROOT") or str(
        Path.home() / "Library/Android/sdk"
    )
    adb_path = os.environ.get("ADB_PATH") or str(
        Path(android_sdk_root) / "platform-tools/adb"
    )
    return RuntimeConfig(
        appium_url=os.environ.get("APPIUM_SERVER_URL", DEFAULT_APPIUM_URL),
        device_serial=os.environ.get("ANDROID_DEVICE_SERIAL", DEFAULT_DEVICE_SERIAL),
        model_provider=model_provider,
        model_name=model_name,
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gemini_model=gemini_model,
        lmstudio_api_key=os.environ.get("LMSTUDIO_API_KEY"),
        lmstudio_model=lmstudio_model,
        lmstudio_base_url=os.environ.get("LMSTUDIO_BASE_URL", DEFAULT_LMSTUDIO_BASE_URL).rstrip("/"),
        runs_dir=Path(os.environ.get("AGENT_RUNNER_RUNS_DIR", DEFAULT_RUNS_DIR)),
        skills_dir=Path(os.environ.get("AGENT_RUNNER_SKILLS_DIR", DEFAULT_SKILLS_DIR)),
        system_skill_file=Path(os.environ.get("AGENT_RUNNER_SYSTEM_SKILL_FILE", DEFAULT_SYSTEM_SKILL_FILE)),
        adb_path=adb_path,
        android_sdk_root=android_sdk_root,
    )


APP_REGISTRY: dict[str, AppConfig] = {
    "amazon": AppConfig(
        name="amazon",
        package_name="com.amazon.mShop.android.shopping",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[
            "buy now",
            "place your order",
            "submit order",
            "checkout",
            "add payment",
            "change password",
            "delete",
            "confirm purchase",
            "message seller",
        ],
        high_risk_signatures=[
            "place your order",
            "buy now",
            "review your order",
            "payment method",
            "one-click",
        ],
        manual_login_tokens=[
            "sign in",
            "enter password",
            "use otp",
            "verification code",
            "forgot password",
        ],
        default_goal_hint="Find the latest order status without making purchases or editing the account.",
    ),
    "settings": AppConfig(
        name="settings",
        package_name="com.android.settings",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["reset", "factory", "erase", "delete"],
        high_risk_signatures=["factory reset", "erase all data"],
        manual_login_tokens=[],
        default_goal_hint="Navigate and inspect settings pages without changing system state.",
    ),
    "facebook": AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=".activity.FbMainTabActivity",
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[
            "buy now",
            "checkout",
            "contact seller",
            "message seller",
            "send",
            "place order",
            "list item",
            "publish",
            "delete",
            "remove",
        ],
        high_risk_signatures=[
            "buy now",
            "contact seller",
            "message seller",
            "checkout",
            "payment",
            "publish listing",
            "delete listing",
        ],
        manual_login_tokens=["log in", "login", "password", "verification", "checkpoint", "code"],
        default_goal_hint="Open Facebook, navigate to Marketplace, inspect local listings read-only, and stop before messaging, buying, or publishing anything.",
    ),
    "fivesurveys": AppConfig(
        name="fivesurveys",
        package_name="com.fivesurveys.mobile",
        launch_activity=".MainActivity",
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[
            "cash out",
            "withdraw",
            "redeem",
            "paypal",
            "visa",
            "payout",
            "bank",
            "submit",
            "complete survey",
            "refer",
            "invite",
            "delete account",
        ],
        high_risk_signatures=[
            "cash out",
            "withdraw",
            "paypal",
            "visa",
            "redeem reward",
            "bank account",
            "complete survey",
        ],
        manual_login_tokens=[
            "log in",
            "sign up",
            "email",
            "password",
            "verification",
            "continue with google",
            "continue with facebook",
        ],
        default_goal_hint="Open Five Surveys, inspect the onboarding surface, and stop before logging in, signing up, answering surveys, or touching payout flows.",
    ),
}


def get_app_config(app_name: str) -> AppConfig:
    try:
        return APP_REGISTRY[app_name]
    except KeyError as exc:
        supported = ", ".join(sorted(APP_REGISTRY))
        raise KeyError(f"Unknown app '{app_name}'. Supported apps: {supported}") from exc


def list_app_configs() -> list[AppConfig]:
    return [APP_REGISTRY[name] for name in sorted(APP_REGISTRY)]


def _load_local_env_files() -> None:
    for candidate in [Path(".env.local"), Path(".env")]:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


APP_REGISTRY.update(
    {
        "chrome": AppConfig(
            name="chrome",
            package_name="com.android.chrome",
            launch_activity=None,
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "payment",
                "checkout",
                "submit",
                "sign in",
                "delete",
            ],
            high_risk_signatures=["payment", "checkout", "confirm form resubmission"],
            manual_login_tokens=["sign in", "enter password", "verification"],
            default_goal_hint="Open Chrome and inspect the current start page without submitting forms.",
        ),
        "clock": AppConfig(
            name="clock",
            package_name="com.google.android.deskclock",
            launch_activity=None,
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=["delete", "remove alarm"],
            high_risk_signatures=["delete alarm", "clear timers"],
            manual_login_tokens=[],
            default_goal_hint="Open Clock and inspect the current tab without destructive changes.",
        ),
        "playstore": AppConfig(
            name="playstore",
            package_name="com.android.vending",
            launch_activity=None,
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "buy",
                "purchase",
                "subscribe",
                "购买",
                "订阅",
            ],
            high_risk_signatures=[
                "purchase",
                "subscribe",
                "buy now",
                "price",
                "价格",
            ],
            manual_login_tokens=["sign in", "enter password", "verification"],
            default_goal_hint="Search the Play Store, open a free app or game page, install it only when explicitly requested, then stop when Open or Play appears.",
        ),
        "gmail": AppConfig(
            name="gmail",
            package_name="com.google.android.gm",
            launch_activity=".ConversationListActivityGmail",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "compose",
                "send",
                "reply",
                "reply all",
                "forward",
                "archive",
                "delete",
                "mark as spam",
                "report phishing",
                "unsubscribe",
                "move to",
                "label",
            ],
            high_risk_signatures=[
                "send",
                "reply",
                "reply all",
                "forward",
                "compose",
                "draft",
                "trash",
            ],
            manual_login_tokens=["sign in", "enter password", "verification", "choose an account"],
            default_goal_hint="Open Gmail, inspect the inbox read-only, and stop without composing, replying, deleting, or archiving.",
        ),
        "youtube": AppConfig(
            name="youtube",
            package_name="com.google.android.youtube",
            launch_activity=".app.honeycomb.Shell$HomeActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "upload",
                "go live",
                "create short",
                "comment",
                "post",
                "purchase",
                "buy",
                "join",
                "membership",
                "super thanks",
                "super chat",
            ],
            high_risk_signatures=[
                "upload",
                "go live",
                "comment",
                "join",
                "membership",
                "super thanks",
                "super chat",
            ],
            manual_login_tokens=["sign in", "enter password", "verification", "choose an account"],
            default_goal_hint="Open YouTube, search for a channel or video, inspect it safely, and require explicit user approval before subscribing or other account actions.",
        ),
        "opinionrewards": AppConfig(
            name="opinionrewards",
            package_name="com.google.android.apps.paidtasks",
            launch_activity=".activity.LaunchActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "redeem",
                "cash out",
                "payment method",
                "submit",
                "answer",
                "confirm",
                "buy",
            ],
            high_risk_signatures=[
                "redeem",
                "cash out",
                "submit survey",
                "payment method",
            ],
            manual_login_tokens=["sign in", "continue", "verification", "choose an account"],
            default_goal_hint="Open Google Opinion Rewards, inspect survey availability and balance read-only, and stop before answering surveys or redeeming anything.",
        ),
        "bing": AppConfig(
            name="bing",
            package_name="com.microsoft.bing",
            launch_activity="com.microsoft.sapphire.app.main.SapphireMainActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "redeem",
                "purchase",
                "buy",
                "claim",
                "checkout",
                "pay",
                "submit",
            ],
            high_risk_signatures=[
                "redeem",
                "checkout",
                "payment",
                "claim reward",
            ],
            manual_login_tokens=["sign in", "enter password", "verification", "choose an account"],
            default_goal_hint="Open Microsoft Bing, inspect Copilot Search or Microsoft Rewards surfaces read-only, and stop before redeeming points, signing in, or submitting forms.",
        ),
        "crowdtap": AppConfig(
            name="crowdtap",
            package_name="com.suzy.droid",
            launch_activity="crc64fb407d7fb80034b3.MainActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "redeem",
                "cash out",
                "gift card",
                "submit",
                "answer",
                "confirm",
            ],
            high_risk_signatures=[
                "redeem",
                "gift card",
                "submit survey",
                "cash out",
            ],
            manual_login_tokens=["sign in", "log in", "password", "verification", "continue"],
            default_goal_hint="Open Crowdtap, inspect the current surface conservatively, and stop if the app blocks screenshots or requires login.",
        ),
        "cashgiraffe": AppConfig(
            name="cashgiraffe",
            package_name="cashgiraffe.app",
            launch_activity="de.mcoins.applike.LauncherDefault",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "cash out",
                "redeem",
                "withdraw",
                "gift card",
                "paypal",
                "purchase",
                "buy",
                "payment method",
                "submit",
            ],
            high_risk_signatures=[
                "cash out",
                "redeem",
                "gift card",
                "paypal",
                "withdraw",
                "payment method",
            ],
            manual_login_tokens=["sign in", "log in", "password", "verification", "continue with google"],
            default_goal_hint="Open Cash Giraffe, inspect the onboarding or offers surface conservatively, and stop before signing in, cashing out, or consenting to payment flows.",
        ),
        "justplay": AppConfig(
            name="justplay",
            package_name="com.justplay.app",
            launch_activity=".offersList.OffersListActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "cash out",
                "redeem",
                "withdraw",
                "gift card",
                "paypal",
                "purchase",
                "buy",
                "payment method",
                "submit",
            ],
            high_risk_signatures=[
                "cash out",
                "redeem",
                "gift card",
                "paypal",
                "withdraw",
                "payment method",
            ],
            manual_login_tokens=["sign in", "log in", "password", "verification", "continue with google"],
            default_goal_hint="Open JustPlay, inspect the onboarding or offers surface conservatively, and stop before signing in, cashing out, or consenting to payment flows.",
        ),
        "moneytime": AppConfig(
            name="moneytime",
            package_name="com.money.time",
            launch_activity=".MainActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
            blocked_keywords=[
                "cash out",
                "cashout with paypal",
                "paypal",
                "gift card",
                "withdraw",
                "redeem",
                "payment method",
                "purchase",
                "buy",
                "submit",
            ],
            high_risk_signatures=[
                "cash out",
                "cashout with paypal",
                "gift card",
                "withdraw",
                "paypal",
                "payment method",
            ],
            manual_login_tokens=["sign in", "log in", "password", "verification", "continue with google"],
            default_goal_hint="Open Money Time, inspect the current earning surface or tracked games conservatively, and stop before cashing out, linking payment accounts, or accepting new permissions.",
        ),
        "swordslash": AppConfig(
            name="swordslash",
            package_name="com.hideseek.swordslash",
            launch_activity="com.unity3d.player.UnityPlayerActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "tool", "stop"],
            blocked_keywords=["purchase", "buy", "subscribe", "watch ad", "shop", "offer"],
            high_risk_signatures=["purchase", "subscribe", "shop", "special offer"],
            manual_login_tokens=[],
            default_goal_hint="Open Sword Slash, do brief safe gameplay to keep the tracked session alive, and stop without purchases or ad-driven reward flows.",
        ),
        "ballsortpuzzle": AppConfig(
            name="ballsortpuzzle",
            package_name="com.hideseek.fruitsortpuzzle",
            launch_activity="com.unity3d.player.UnityPlayerActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "tool", "stop"],
            blocked_keywords=["purchase", "buy", "subscribe", "watch ad", "shop", "offer"],
            high_risk_signatures=["purchase", "subscribe", "shop", "special offer"],
            manual_login_tokens=[],
            default_goal_hint="Open Ball Sort Puzzle, progress through the first playable moves safely, and stop without purchases or rewarded-ad flows.",
        ),
        "juicycandyquest": AppConfig(
            name="juicycandyquest",
            package_name="com.hideseek.juicycandyquest",
            launch_activity="com.unity3d.player.UnityPlayerActivity",
            allowed_actions=["tap", "back", "home", "wait", "swipe", "tool", "stop"],
            blocked_keywords=["purchase", "buy", "subscribe", "watch ad", "shop", "offer"],
            high_risk_signatures=["purchase", "subscribe", "shop", "special offer"],
            manual_login_tokens=[],
            default_goal_hint="Open Juicy Candy Quest, clear the first tutorial prompt and start level 1 safely, then stop without purchases or rewarded-ad flows.",
        ),
    }
)
