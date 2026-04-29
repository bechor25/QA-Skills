"""
E2E tests for the login page (/login).
Requires the app to be running: uvicorn app.main:app --port 8000
"""
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8000"

# Seed credentials — must match a real user in the test DB
VALID_EMAIL = "e2e@example.com"
VALID_PASSWORD = "E2ePass1!"


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

class TestLoginFlow:
    def test_login_page_loads(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        expect(page).to_have_title("Login")
        expect(page.get_by_role("heading", name="Sign In")).to_be_visible()

    def test_email_and_password_inputs_visible(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        expect(page.locator("#email")).to_be_visible()
        expect(page.locator("#password")).to_be_visible()
        expect(page.get_by_role("button", name="Sign In")).to_be_visible()

    def test_valid_credentials_store_token_and_redirect(self, page: Page):
        page.route("**/auth/login", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"token": "test.jwt.token", "token_type": "bearer"}',
        ))
        # Route /dashboard so navigation doesn't 404-crash the context
        page.route("**/dashboard", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<html><body><p>Dashboard</p></body></html>",
        ))
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        page.locator("#email").fill(VALID_EMAIL)
        page.locator("#password").fill(VALID_PASSWORD)
        page.get_by_role("button", name="Sign In").click()

        # Wait for redirect to complete
        page.wait_for_url("**/dashboard", timeout=5000)

        token = page.evaluate("localStorage.getItem('token')")
        assert token == "test.jwt.token", "Token not stored in localStorage"

    def test_invalid_credentials_show_error(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        page.locator("#email").fill("wrong@example.com")
        page.locator("#password").fill("WrongPass!")
        page.get_by_role("button", name="Sign In").click()

        expect(page.locator("#error-message")).to_be_visible()
        expect(page.locator("#error-message")).to_contain_text("Invalid credentials")

    def test_error_message_hidden_on_page_load(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        error_el = page.locator("#error-message")
        hidden = page.evaluate("document.getElementById('error-message').hidden")
        assert hidden is True, "Error message visible on initial load"

    def test_api_failure_shows_error_message(self, page: Page):
        page.route("**/auth/login", lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail": "Internal Server Error"}',
        ))
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("any@example.com")
        page.locator("#password").fill("AnyPass1!")
        page.get_by_role("button", name="Sign In").click()

        expect(page.locator("#error-message")).to_be_visible()

    def test_401_response_shows_error_not_blank(self, page: Page):
        page.route("**/auth/login", lambda route: route.fulfill(
            status=401,
            content_type="application/json",
            body='{"detail": "Invalid credentials"}',
        ))
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("any@example.com")
        page.locator("#password").fill("AnyPass1!")
        page.get_by_role("button", name="Sign In").click()

        expect(page.locator("#error-message")).to_be_visible()
        expect(page.locator("body")).not_to_contain_text("Internal Server Error")


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------

class TestFormValidation:
    def test_submit_empty_form_shows_browser_validation(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.get_by_role("button", name="Sign In").click()
        # HTML5 required prevents submission — no network request fired
        requests_made = []
        page.on("request", lambda r: requests_made.append(r.url))
        assert not any("/auth/login" in r for r in requests_made)

    def test_invalid_email_format_blocked_by_browser(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("not-an-email")
        page.locator("#password").fill("SomePass1!")
        page.get_by_role("button", name="Sign In").click()
        # Email type input with invalid format blocks submission
        validity = page.evaluate("document.getElementById('email').validity.valid")
        assert validity is False

    def test_paste_into_email_field_works(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        email_input = page.locator("#email")
        email_input.click()
        page.keyboard.insert_text("pasted@example.com")
        expect(email_input).to_have_value("pasted@example.com")

    def test_password_field_masked(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        input_type = page.locator("#password").get_attribute("type")
        assert input_type == "password", "Password field not masked"


# ---------------------------------------------------------------------------
# Accessibility
# ---------------------------------------------------------------------------

class TestAccessibility:
    def test_email_input_has_label(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        label_count = page.locator('label[for="email"]').count()
        assert label_count == 1, "Email input missing <label>"

    def test_password_input_has_label(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        label_count = page.locator('label[for="password"]').count()
        assert label_count == 1, "Password input missing <label>"

    def test_inputs_marked_required(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        email_required = page.evaluate("document.getElementById('email').required")
        password_required = page.evaluate("document.getElementById('password').required")
        assert email_required is True
        assert password_required is True

    def test_error_div_has_alert_role(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        role = page.locator("#error-message").get_attribute("role")
        assert role == "alert", "Error container missing role='alert'"

    def test_error_div_has_aria_live(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        aria_live = page.locator("#error-message").get_attribute("aria-live")
        assert aria_live == "polite"

    def test_submit_button_has_text(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        btn = page.get_by_role("button", name="Sign In")
        text = btn.inner_text()
        assert text.strip() != "", "Submit button has no text"

    def test_keyboard_tab_reaches_all_form_fields(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.keyboard.press("Tab")
        focused = page.evaluate("document.activeElement.id")
        assert focused == "email"

        page.keyboard.press("Tab")
        focused = page.evaluate("document.activeElement.id")
        assert focused == "password"

    def test_enter_key_submits_form(self, page: Page):
        submitted = []
        page.route("**/auth/login", lambda route: (submitted.append(True), route.fulfill(
            status=401,
            content_type="application/json",
            body='{"detail": "Invalid credentials"}',
        )))
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("test@example.com")
        page.locator("#password").fill("Pass123!")
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        assert len(submitted) > 0, "Enter key did not submit the form"


# ---------------------------------------------------------------------------
# Visual / network
# ---------------------------------------------------------------------------

class TestVisualAndNetwork:
    def test_no_token_in_localstorage_on_page_load(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        token = page.evaluate("localStorage.getItem('token')")
        assert token is None

    def test_successful_login_stores_token_as_string(self, page: Page):
        page.route("**/auth/login", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"token": "fake.jwt.token", "token_type": "bearer"}',
        ))
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("any@example.com")
        page.locator("#password").fill("AnyPass1!")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_load_state("networkidle")

        token = page.evaluate("localStorage.getItem('token')")
        assert token == "fake.jwt.token"

    def test_login_request_sends_json_content_type(self, page: Page):
        captured_headers = {}
        def capture(route):
            captured_headers.update(route.request.headers)
            route.fulfill(status=401, content_type="application/json", body='{"detail":"x"}')
        page.route("**/auth/login", capture)

        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("test@example.com")
        page.locator("#password").fill("Pass123!")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_load_state("networkidle")

        assert "application/json" in captured_headers.get("content-type", ""), \
            "Login request not sending Content-Type: application/json"

    def test_login_request_body_has_email_and_password(self, page: Page):
        captured_body = {}
        import json

        def capture(route):
            try:
                captured_body.update(json.loads(route.request.post_data or "{}"))
            except Exception:
                pass
            route.fulfill(status=401, content_type="application/json", body='{"detail":"x"}')

        page.route("**/auth/login", capture)
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("myemail@example.com")
        page.locator("#password").fill("MyPass1!")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_load_state("networkidle")

        assert captured_body.get("email") == "myemail@example.com"
        assert captured_body.get("password") == "MyPass1!"

    def test_network_error_shows_error_not_blank_page(self, page: Page):
        page.route("**/auth/login", lambda route: route.abort("failed"))
        page.goto(f"{BASE_URL}/login")
        page.locator("#email").fill("any@example.com")
        page.locator("#password").fill("AnyPass1!")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_load_state("networkidle")
        # Page should not be blank
        body_text = page.locator("body").inner_text()
        assert len(body_text.strip()) > 0, "Page blank after network failure"
