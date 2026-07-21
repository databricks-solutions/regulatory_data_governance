import os
import unittest
from unittest.mock import patch

from app.backend.dqx_config import dqx_studio_base_url


class DqxStudioBaseUrlTest(unittest.TestCase):
    def test_missing_value_is_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(dqx_studio_base_url())

    def test_bundle_sentinel_is_unset(self):
        with patch.dict(os.environ, {"DQX_STUDIO_URL": "about:blank"}, clear=True):
            self.assertIsNone(dqx_studio_base_url())

    def test_configured_url_is_trimmed_and_has_no_trailing_slash(self):
        with patch.dict(
            os.environ,
            {"DQX_STUDIO_URL": "  https://dqx.example.databricksapps.com/  "},
            clear=True,
        ):
            self.assertEqual(
                dqx_studio_base_url(),
                "https://dqx.example.databricksapps.com",
            )


if __name__ == "__main__":
    unittest.main()
