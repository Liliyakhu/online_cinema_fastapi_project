from notifications.interfaces import EmailSenderInterface


class StubEmailSender(EmailSenderInterface):
    async def send_activation_email(self, email: str, activation_link: str) -> None:
        pass

    async def send_activation_complete_email(self, email: str, login_link: str) -> None:
        pass

    async def send_password_reset_email(self, email: str, reset_link: str) -> None:
        pass

    async def send_password_reset_complete_email(self, email: str, login_link: str) -> None:
        pass

    async def send_order_confirmation_email(self, email: str, order_id: int, total_amount: str) -> None:
        pass
