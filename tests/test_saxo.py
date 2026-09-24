import pytest

from cheshire_cat.saxo import SaxoConfig, SaxoOpenAPI


def test_saxo_defaults_to_sim_and_preview_never_sends():
    config = SaxoConfig(access_token="token")
    assert config.base_url.endswith("/sim/openapi")
    preview = SaxoOpenAPI.preview_order(
        account_key="account",
        uic=42,
        asset_type="Stock",
        buy_sell="Buy",
        amount=3,
    )
    assert preview["Uic"] == 42
    assert preview["ManualOrder"] is True


def test_saxo_order_placement_requires_opt_in_and_confirmation():
    class Session:
        headers = {}

        def post(self, *args, **kwargs):
            raise AssertionError("must not send a disabled order")

    client = SaxoOpenAPI(SaxoConfig(access_token="token"), session=Session())
    with pytest.raises(PermissionError):
        client.place_order({"Amount": 1}, confirm="PLACE_ORDER")
