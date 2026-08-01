import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "synthetic-screens"
WIDTH = 1080
HEIGHT = 1920

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/NotoSansKR-Regular.otf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]
BOLD_CANDIDATES = [
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    Path("C:/Windows/Fonts/NotoSansKR-Bold.otf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
]

SCREEN_MANIFEST = [
    {
        "filename": "subscription-cancel-retention.png",
        "category": "subscription_cancellation",
        "risk_fixture": "high",
        "notes": "Prominent retention button, smaller cancellation continuation.",
    },
    {
        "filename": "subscription-cancel-confirmation.png",
        "category": "subscription_cancellation",
        "risk_fixture": "low",
        "notes": "Final confirmation screen with direct cancellation completion.",
    },
    {
        "filename": "subscription-pause-offer.png",
        "category": "subscription_cancellation",
        "risk_fixture": "medium",
        "notes": "Pause offer competes with cancellation continuation.",
    },
    {
        "filename": "trial-renewal-warning.png",
        "category": "trial_cancellation",
        "risk_fixture": "high",
        "notes": "Auto-renewal charge and prominent extension action.",
    },
    {
        "filename": "trial-discount-retention.png",
        "category": "trial_cancellation",
        "risk_fixture": "high",
        "notes": "Discount continuation offer before cancellation.",
    },
    {
        "filename": "trial-cancel-success.png",
        "category": "trial_cancellation",
        "risk_fixture": "low",
        "notes": "Cancellation success / no next billing.",
    },
    {
        "filename": "checkout-preselected-addon.png",
        "category": "checkout_addons",
        "risk_fixture": "high",
        "notes": "Paid optional add-ons selected by default.",
    },
    {
        "filename": "checkout-donation-addon.png",
        "category": "checkout_addons",
        "risk_fixture": "medium",
        "notes": "Optional donation selected by default.",
    },
    {
        "filename": "checkout-warranty-addon.png",
        "category": "checkout_addons",
        "risk_fixture": "high",
        "notes": "Warranty add-on selected by default.",
    },
    {
        "filename": "checkout-no-preselected-addon.png",
        "category": "checkout_addons",
        "risk_fixture": "low",
        "notes": "Optional add-ons visible but unchecked.",
    },
    {
        "filename": "marketing-consent-optional.png",
        "category": "marketing_consent",
        "risk_fixture": "high",
        "notes": "Agree-all and optional marketing choices selected.",
    },
    {
        "filename": "marketing-separated-optional.png",
        "category": "marketing_consent",
        "risk_fixture": "low",
        "notes": "Optional marketing choices are separated and unchecked.",
    },
    {
        "filename": "consent-required-only.png",
        "category": "marketing_consent",
        "risk_fixture": "low",
        "notes": "Required consent only.",
    },
    {
        "filename": "account-delete-retention.png",
        "category": "account_deletion",
        "risk_fixture": "high",
        "notes": "Prominent keep-account button and smaller deletion continuation.",
    },
    {
        "filename": "account-delete-confirmation.png",
        "category": "account_deletion",
        "risk_fixture": "low",
        "notes": "Final account deletion confirmation.",
    },
]

CATEGORY_GOALS = {
    "subscription_cancellation": "cancel_subscription",
    "trial_cancellation": "cancel_trial",
    "checkout_addons": "buy_without_addons",
    "marketing_consent": "reject_marketing",
    "account_deletion": "delete_account",
}


def _font_path(bold: bool) -> Path | None:
    for candidate in BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = _font_path(bold)
    if path:
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    fill: str,
    size: int,
    bold: bool = False,
    line_gap: int = 12,
) -> int:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    text_font = font(size, bold)
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=text_font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=text_font, fill=fill)
        y += size + line_gap
    return y


def base_screen(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#F7F8FA")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, WIDTH, 170), radius=0, fill="#FFFFFF")
    draw.text((58, 58), title, font=font(40, True), fill="#15171A")
    draw.text((58, 116), subtitle, font=font(24), fill="#5D6670")
    return image, draw


def button(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    fill: str,
    outline: str | None = None,
    text_fill: str = "#FFFFFF",
) -> None:
    draw.rounded_rectangle(box, radius=28, fill=fill, outline=outline, width=3 if outline else 1)
    text_font = font(32, True)
    tw = draw.textlength(label, font=text_font)
    x1, y1, x2, y2 = box
    draw.text(((x1 + x2 - tw) / 2, y1 + (y2 - y1 - 40) / 2), label, font=text_font, fill=text_fill)


def checkbox(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    checked: bool,
    helper: str | None = None,
) -> None:
    draw.rounded_rectangle((x, y, x + 54, y + 54), radius=10, outline="#2E6F68", width=4, fill="#FFFFFF")
    if checked:
        draw.line((x + 13, y + 28, x + 24, y + 40, x + 42, y + 15), fill="#2E6F68", width=7, joint="curve")
    draw.text((x + 78, y - 2), label, font=font(29, True), fill="#17191D")
    if helper:
        draw.text((x + 78, y + 44), helper, font=font(22), fill="#69737D")


def info_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, body: str) -> None:
    draw.rounded_rectangle(box, radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    x1, y1, x2, _ = box
    draw.text((x1 + 46, y1 + 46), title, font=font(38, True), fill="#17191D")
    draw_wrapped(draw, body, (x1 + 46, y1 + 112), x2 - x1 - 92, "#59636E", 27)


def subscription_cancel() -> None:
    image, draw = base_screen("멤버십 해지", "혜택을 마지막으로 확인")
    info_card(
        draw,
        (58, 230, 1022, 590),
        "이번 달 혜택을 포기하시겠어요?",
        "무료 배송, 멤버 전용 할인, 쿠폰 혜택은 해지 즉시 더 이상 받을 수 없습니다.",
    )
    button(draw, (74, 720, 1006, 850), "혜택 계속 받기", "#2E6F68")
    button(draw, (74, 890, 1006, 1010), "계속 해지하기", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    draw.text(
        (82, 1090),
        "작게 표시된 해지 버튼을 눌러야 다음 단계로 이동합니다.",
        font=font(25),
        fill="#8A4B1B",
    )
    image.save(OUT / "subscription-cancel-retention.png")


def subscription_cancel_confirmation() -> None:
    image, draw = base_screen("멤버십 해지", "마지막 확인 단계")
    info_card(
        draw,
        (58, 230, 1022, 590),
        "해지를 완료하시겠습니까?",
        "해지 후 다음 결제일부터 요금이 청구되지 않습니다. 오늘까지는 남은 혜택을 사용할 수 있습니다.",
    )
    button(draw, (74, 720, 1006, 850), "해지 완료하기", "#17191D")
    button(draw, (74, 895, 1006, 1015), "이전으로", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    image.save(OUT / "subscription-cancel-confirmation.png")


def subscription_pause_offer() -> None:
    image, draw = base_screen("멤버십 해지", "잠시 멈춤 제안")
    info_card(
        draw,
        (58, 230, 1022, 590),
        "해지 대신 1개월 일시정지는 어떠세요?",
        "요금은 다음 달부터 다시 청구됩니다. 해지를 계속하려면 아래의 보조 버튼을 선택하세요.",
    )
    button(draw, (74, 720, 1006, 850), "1개월 일시정지", "#2E6F68")
    button(draw, (74, 895, 1006, 1015), "해지 계속하기", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    image.save(OUT / "subscription-pause-offer.png")


def free_trial_cancel() -> None:
    image, draw = base_screen("무료 체험 관리", "자동 결제 전에 선택을 확인")
    info_card(
        draw,
        (58, 230, 1022, 620),
        "내일 오후 11:59에 자동 결제됩니다",
        "무료 체험 종료 후 월 12,900원이 결제됩니다. 취소하지 않으면 멤버십이 자동으로 시작됩니다.",
    )
    button(draw, (74, 720, 1006, 850), "7일 더 무료로 이용하기", "#2E6F68")
    button(draw, (74, 895, 1006, 1015), "지금 체험 취소", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    draw.rounded_rectangle((74, 1125, 1006, 1290), radius=24, fill="#FFF7ED", outline="#F3C789", width=2)
    draw.text((112, 1172), "결제 예정 금액: 12,900원 / 월", font=font(29, True), fill="#8A4B1B")
    draw.text((112, 1222), "취소 후에도 오늘까지는 체험 혜택을 사용할 수 있습니다.", font=font(24), fill="#8A4B1B")
    image.save(OUT / "trial-renewal-warning.png")


def trial_discount_offer() -> None:
    image, draw = base_screen("무료 체험 관리", "결제 전 특별 제안")
    info_card(
        draw,
        (58, 230, 1022, 620),
        "첫 달 50% 할인으로 계속 이용",
        "할인을 선택하면 무료 체험 종료 후 월 6,450원이 자동 결제됩니다.",
    )
    button(draw, (74, 720, 1006, 850), "할인 받고 계속하기", "#2E6F68")
    button(draw, (74, 895, 1006, 1015), "체험 취소 계속", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    image.save(OUT / "trial-discount-retention.png")


def trial_cancel_success() -> None:
    image, draw = base_screen("무료 체험", "취소가 예약되었습니다")
    info_card(
        draw,
        (58, 230, 1022, 600),
        "무료 체험 취소 완료",
        "다음 결제는 진행되지 않습니다. 남은 체험 기간 동안은 서비스를 계속 이용할 수 있습니다.",
    )
    button(draw, (74, 720, 1006, 850), "확인", "#17191D")
    image.save(OUT / "trial-cancel-success.png")


def checkout_addon() -> None:
    image, draw = base_screen("주문 결제", "선택 항목을 확인하세요")
    draw.rounded_rectangle((58, 230, 1022, 1420), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    draw.text((104, 292), "주문 요약", font=font(40, True), fill="#17191D")
    draw.text((104, 370), "상품 금액", font=font(28), fill="#59636E")
    draw.text((780, 370), "29,000원", font=font(28, True), fill="#17191D")
    draw.line((104, 445, 976, 445), fill="#E5E9EF", width=3)
    checkbox(draw, 104, 510, "배송 보험 +2,900원", True, "분실/파손 시 보상")
    checkbox(draw, 104, 660, "무료 멤버십 체험", True, "7일 후 월 9,900원 자동결제")
    checkbox(draw, 104, 810, "할인 알림 받기", False, "선택 동의")
    draw.line((104, 1010, 976, 1010), fill="#E5E9EF", width=3)
    draw.text((104, 1082), "총 결제 금액", font=font(32, True), fill="#17191D")
    draw.text((748, 1082), "31,900원", font=font(36, True), fill="#B23B2D")
    button(draw, (104, 1235, 976, 1360), "결제하기", "#17191D")
    image.save(OUT / "checkout-preselected-addon.png")


def checkout_donation_addon() -> None:
    image, draw = base_screen("주문 결제", "추가 선택 항목")
    draw.rounded_rectangle((58, 230, 1022, 1320), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    draw.text((104, 292), "주문 요약", font=font(40, True), fill="#17191D")
    draw.text((104, 370), "상품 금액", font=font(28), fill="#59636E")
    draw.text((780, 370), "18,000원", font=font(28, True), fill="#17191D")
    draw.line((104, 445, 976, 445), fill="#E5E9EF", width=3)
    checkbox(draw, 104, 510, "환경 기부금 +1,000원", True, "선택 항목")
    checkbox(draw, 104, 660, "포장 업그레이드 +1,500원", False, "선택 항목")
    draw.line((104, 900, 976, 900), fill="#E5E9EF", width=3)
    draw.text((104, 970), "총 결제 금액", font=font(32, True), fill="#17191D")
    draw.text((760, 970), "19,000원", font=font(36, True), fill="#B23B2D")
    button(draw, (104, 1145, 976, 1270), "결제하기", "#17191D")
    image.save(OUT / "checkout-donation-addon.png")


def checkout_warranty_addon() -> None:
    image, draw = base_screen("주문 결제", "보증 옵션 확인")
    draw.rounded_rectangle((58, 230, 1022, 1320), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    draw.text((104, 292), "주문 요약", font=font(40, True), fill="#17191D")
    draw.text((104, 370), "상품 금액", font=font(28), fill="#59636E")
    draw.text((780, 370), "74,000원", font=font(28, True), fill="#17191D")
    draw.line((104, 445, 976, 445), fill="#E5E9EF", width=3)
    checkbox(draw, 104, 510, "연장 보증 +6,900원", True, "선택 항목")
    checkbox(draw, 104, 660, "빠른 배송 +3,000원", False, "선택 항목")
    draw.line((104, 900, 976, 900), fill="#E5E9EF", width=3)
    draw.text((104, 970), "총 결제 금액", font=font(32, True), fill="#17191D")
    draw.text((760, 970), "80,900원", font=font(36, True), fill="#B23B2D")
    button(draw, (104, 1145, 976, 1270), "결제하기", "#17191D")
    image.save(OUT / "checkout-warranty-addon.png")


def checkout_clean() -> None:
    image, draw = base_screen("주문 결제", "선택 항목을 확인하세요")
    draw.rounded_rectangle((58, 230, 1022, 1420), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    draw.text((104, 292), "주문 요약", font=font(40, True), fill="#17191D")
    draw.text((104, 370), "상품 금액", font=font(28), fill="#59636E")
    draw.text((780, 370), "29,000원", font=font(28, True), fill="#17191D")
    draw.line((104, 445, 976, 445), fill="#E5E9EF", width=3)
    checkbox(draw, 104, 510, "배송 보험 +2,900원", False, "선택하지 않음")
    checkbox(draw, 104, 660, "무료 멤버십 체험", False, "선택하지 않음")
    checkbox(draw, 104, 810, "할인 알림 받기", False, "선택 동의")
    draw.line((104, 1010, 976, 1010), fill="#E5E9EF", width=3)
    draw.text((104, 1082), "총 결제 금액", font=font(32, True), fill="#17191D")
    draw.text((748, 1082), "29,000원", font=font(36, True), fill="#17191D")
    button(draw, (104, 1235, 976, 1360), "결제하기", "#17191D")
    image.save(OUT / "checkout-no-preselected-addon.png")


def marketing_consent() -> None:
    image, draw = base_screen("약관 동의", "필수와 선택을 구분하세요")
    button(draw, (58, 240, 1022, 370), "전체 동의", "#2E6F68")
    draw.rounded_rectangle((58, 450, 1022, 1320), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    checkbox(draw, 104, 540, "서비스 이용약관 동의", True, "필수")
    checkbox(draw, 104, 700, "개인정보 수집 및 이용", True, "필수")
    checkbox(draw, 104, 860, "마케팅 정보 수신", True, "선택")
    checkbox(draw, 104, 1020, "제휴사 혜택 알림", True, "선택")
    draw.text((104, 1210), "선택 항목은 거절해도 가입을 계속할 수 있습니다.", font=font(25), fill="#8A4B1B")
    button(draw, (58, 1450, 1022, 1580), "다음", "#17191D")
    image.save(OUT / "marketing-consent-optional.png")


def marketing_separated_optional() -> None:
    image, draw = base_screen("약관 동의", "선택 동의는 분리되어 있습니다")
    draw.rounded_rectangle((58, 260, 1022, 1220), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    checkbox(draw, 104, 360, "서비스 이용약관 동의", True, "필수")
    checkbox(draw, 104, 520, "개인정보 수집 및 이용", True, "필수")
    checkbox(draw, 104, 700, "마케팅 정보 수신", False, "선택하지 않음")
    checkbox(draw, 104, 860, "제휴사 혜택 알림", False, "선택하지 않음")
    button(draw, (58, 1400, 1022, 1530), "다음", "#17191D")
    image.save(OUT / "marketing-separated-optional.png")


def required_terms_only() -> None:
    image, draw = base_screen("약관 동의", "필수 항목만 확인하세요")
    draw.rounded_rectangle((58, 260, 1022, 1030), radius=30, fill="#FFFFFF", outline="#DEE3EA", width=2)
    checkbox(draw, 104, 360, "서비스 이용약관 동의", True, "필수")
    checkbox(draw, 104, 520, "개인정보 수집 및 이용", True, "필수")
    draw.text((104, 730), "선택 마케팅 동의 항목은 이 화면에 없습니다.", font=font(25), fill="#2E6F68")
    button(draw, (58, 1180, 1022, 1310), "다음", "#17191D")
    image.save(OUT / "consent-required-only.png")


def account_delete() -> None:
    image, draw = base_screen("회원 탈퇴", "계정을 삭제하기 전에 확인")
    info_card(
        draw,
        (58, 230, 1022, 620),
        "탈퇴하면 저장된 정보가 삭제됩니다",
        "프로필, 저장 목록, 포인트 내역이 삭제될 수 있습니다. 탈퇴를 계속하려면 아래의 작은 버튼을 선택하세요.",
    )
    button(draw, (74, 720, 1006, 850), "계정 유지하기", "#2E6F68")
    button(draw, (74, 895, 1006, 1015), "계속 탈퇴하기", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    draw.rounded_rectangle((74, 1125, 1006, 1300), radius=24, fill="#FFF3F0", outline="#F2B5A8", width=2)
    draw.text((112, 1172), "탈퇴 전 확인", font=font(29, True), fill="#9B3529")
    draw.text((112, 1222), "삭제 후 일부 데이터는 복구할 수 없습니다.", font=font(24), fill="#9B3529")
    image.save(OUT / "account-delete-retention.png")


def account_delete_confirmation() -> None:
    image, draw = base_screen("회원 탈퇴", "최종 확인")
    info_card(
        draw,
        (58, 230, 1022, 620),
        "정말 탈퇴를 완료하시겠습니까?",
        "탈퇴 완료 후 프로필과 저장 목록은 복구할 수 없습니다. 계속하려면 탈퇴 완료 버튼을 선택하세요.",
    )
    button(draw, (74, 720, 1006, 850), "탈퇴 완료하기", "#17191D")
    button(draw, (74, 895, 1006, 1015), "이전으로", "#FFFFFF", outline="#BBC5D1", text_fill="#30363D")
    image.save(OUT / "account-delete-confirmation.png")


def write_manifest() -> None:
    screens = [
        {
            **screen,
            "recommended_goal_id": CATEGORY_GOALS[screen["category"]],
        }
        for screen in SCREEN_MANIFEST
    ]
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "description": "Synthetic Korean UI screenshots for ExitGuide AI demos.",
                "screen_count": len(screens),
                "screens": screens,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    subscription_cancel()
    subscription_cancel_confirmation()
    subscription_pause_offer()
    free_trial_cancel()
    trial_discount_offer()
    trial_cancel_success()
    checkout_addon()
    checkout_donation_addon()
    checkout_warranty_addon()
    checkout_clean()
    marketing_consent()
    marketing_separated_optional()
    required_terms_only()
    account_delete()
    account_delete_confirmation()
    write_manifest()
    print(f"generated screens in {OUT}")


if __name__ == "__main__":
    main()
