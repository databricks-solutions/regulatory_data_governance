import os
import unittest
from unittest.mock import patch

from app.backend.dqx_config import (
    dqx_studio_base_url,
    dqx_studio_entry_path,
    dqx_studio_entry_url,
)


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


class DqxStudioEntryPathTest(unittest.TestCase):
    """Configurável porque a Studio renomeia rotas: `/rules/active` foi
    aposentado e o embed passou a mostrar tela deprecada."""

    def test_default_is_the_rules_registry(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(dqx_studio_entry_path(), "/registry-rules")

    def test_leading_slash_is_added(self):
        with patch.dict(os.environ, {"DQX_STUDIO_ENTRY_PATH": "monitored-tables"}, clear=True):
            self.assertEqual(dqx_studio_entry_path(), "/monitored-tables")

    def test_trailing_slash_is_stripped(self):
        with patch.dict(os.environ, {"DQX_STUDIO_ENTRY_PATH": "/results/"}, clear=True):
            self.assertEqual(dqx_studio_entry_path(), "/results")

    def test_root_means_studio_home(self):
        # `/` é valor válido (home), não "não configurado" — daí não ter sentinela.
        for value in ("/", "  /  "):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DQX_STUDIO_ENTRY_PATH": value}, clear=True):
                    self.assertEqual(dqx_studio_entry_path(), "")

    def test_absolute_url_is_refused(self):
        """Esquema/host apontaria o iframe para fora da Studio."""
        for value in ("https://evil.example.com", "//evil.example.com", "javascript:alert(1)"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DQX_STUDIO_ENTRY_PATH": value}, clear=True):
                    self.assertEqual(dqx_studio_entry_path(), "/registry-rules")


class DqxStudioEntryUrlTest(unittest.TestCase):
    def test_joins_base_and_path(self):
        with patch.dict(
            os.environ,
            {
                "DQX_STUDIO_URL": "https://dqx.example.databricksapps.com/",
                "DQX_STUDIO_ENTRY_PATH": "/registry-rules",
            },
            clear=True,
        ):
            self.assertEqual(
                dqx_studio_entry_url(),
                "https://dqx.example.databricksapps.com/registry-rules",
            )

    def test_home_path_yields_bare_base(self):
        with patch.dict(
            os.environ,
            {"DQX_STUDIO_URL": "https://dqx.example.databricksapps.com", "DQX_STUDIO_ENTRY_PATH": "/"},
            clear=True,
        ):
            self.assertEqual(
                dqx_studio_entry_url(),
                "https://dqx.example.databricksapps.com",
            )

    def test_unset_studio_url_is_none_regardless_of_path(self):
        # É o que faz o Motor de Regras renderizar estado vazio.
        with patch.dict(
            os.environ,
            {"DQX_STUDIO_URL": "about:blank", "DQX_STUDIO_ENTRY_PATH": "/registry-rules"},
            clear=True,
        ):
            self.assertIsNone(dqx_studio_entry_url())


if __name__ == "__main__":
    unittest.main()
