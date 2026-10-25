from django.test import RequestFactory, SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.urls import reverse
import hmac
import hashlib
import json

from shop.models import (
    Categories_from_Category_2nd,
    Category,
    FavoriteProducts,
    Order,
    OrderItem,
    Product,
    Review,
)
from shop.views.payments import yookassa_webhook
from shop.views.services import (
    InsufficientStock,
    cancel_order,
    fail_unpaid_order,
    mark_order_paid,
    reserve_order_stock,
)


def test_webhook_signature():
    secret_key = "your-test-secret-key"
    data = {
        "event": "payment.succeeded",
        "object": {
            "id": "test_payment_id",
            "metadata": {"order_id": 123}
        }
    }
    body = json.dumps(data)
    signature = hmac.new(
        key=secret_key.encode('utf-8'),
        msg=body.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()


class OrderStockReservationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.seller = user_model.objects.create_user(
            username="seller",
            password="test-password",
            role_shopper=True,
        )
        category = Category.objects.create(name="Category", slug="category")
        subcategory = Categories_from_Category_2nd.objects.create(
            category=category,
            brand="Brand",
            slug="brand",
        )
        self.product = Product.objects.create(
            category2nd=subcategory,
            user=self.seller,
            name="Product",
            slug="product",
            price=Decimal("10.00"),
            stock=5,
        )
        self.order = Order.objects.create(
            user=self.seller,
            status="awaiting_payment",
            delivery_address="Test address",
            total_price=Decimal("20.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price=Decimal("10.00"),
            quantity=2,
        )

    def test_payment_does_not_deduct_reserved_stock_twice(self):
        reserve_order_stock(self.order)
        reserve_order_stock(self.order)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

        self.assertTrue(mark_order_paid(self.order, SimpleNamespace(id="pay-1")))

        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.order.status, "pending")
        self.assertTrue(self.order.stock_reserved)

    def test_favorites_page_lists_users_available_products(self):
        FavoriteProducts.objects.create(user=self.seller, product=self.product)
        self.client.force_login(self.seller)

        response = self.client.get(reverse("shop:favorites_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_cancelled_order_releases_reserved_stock_only_once(self):
        reserve_order_stock(self.order)

        self.assertTrue(cancel_order(self.order))
        self.assertFalse(cancel_order(self.order))

        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertFalse(self.order.stock_reserved)

    def test_failed_unpaid_order_releases_reserved_stock(self):
        reserve_order_stock(self.order)

        self.assertTrue(fail_unpaid_order(self.order))

        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.order.status, "failed")
        self.assertFalse(self.order.stock_reserved)

    def test_reservation_does_not_allow_overselling(self):
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        OrderItem.objects.filter(order=self.order).update(quantity=1)

        reserve_order_stock(self.order)

        second_order = Order.objects.create(
            user=self.seller,
            status="awaiting_payment",
            delivery_address="Test address",
            total_price=Decimal("10.00"),
        )
        OrderItem.objects.create(
            order=second_order,
            product=self.product,
            price=Decimal("10.00"),
            quantity=1,
        )

        with self.assertRaises(InsufficientStock):
            reserve_order_stock(second_order)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)


class ReviewSubmissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="reviewer",
            password="test-password",
            role_shopper=True,
        )
        category = Category.objects.create(name="Review category", slug="review-category")
        subcategory = Categories_from_Category_2nd.objects.create(
            category=category,
            brand="Review brand",
            slug="review-brand",
        )
        self.product = Product.objects.create(
            category2nd=subcategory,
            user=self.user,
            name="Review product",
            slug="review-product",
            price=Decimal("10.00"),
        )

    def test_review_is_returned_when_email_notification_times_out(self):
        self.client.force_login(self.user)

        with patch(
            "shop.views.reviews.send_mail",
            side_effect=TimeoutError("mail server timed out"),
        ):
            response = self.client.post(
                reverse(
                    "shop:add_review",
                    args=[self.product.id, self.product.slug],
                ),
                {"text_0": "Минус", "text_1": "Плюс"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Плюс")
        self.assertContains(response, "Минус")
        self.assertTrue(
            Review.objects.filter(
                product=self.product,
                user=self.user,
                text_0="Минус",
                text_1="Плюс",
            ).exists()
        )


class YookassaWebhookTests(SimpleTestCase):
    def test_yookassa_lookup_failure_is_retryable(self):
        request = RequestFactory().post(
            "/payment/webhook/",
            data=json.dumps({"object": {"id": "payment-1"}}),
            content_type="application/json",
        )

        with (
            patch("shop.views.payments.get_client_ip", return_value="185.32.187.10"),
            patch(
                "shop.views.payments.YookassaPayment.find_one",
                side_effect=RuntimeError("temporary API error"),
            ),
        ):
            response = yookassa_webhook(request)

        self.assertEqual(response.status_code, 503)
