import unittest

import app as app_module


class CardScoringApiTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app_module.games.clear()
        self.client = app_module.app.test_client()

    def start_game(self, **overrides):
        payload = {
            "players": [
                {"name": "A", "initial": 0},
                {"name": "B", "initial": 0},
            ],
            "admin_mode": "none",
            "admin_config": {},
        }
        payload.update(overrides)
        return self.client.post("/api/start", json=payload)

    def test_start_rejects_duplicate_player_names(self):
        res = self.start_game(
            players=[
                {"name": "A", "initial": 0},
                {"name": "A", "initial": 0},
            ]
        )

        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_start_rejects_invalid_fixed_admin_index(self):
        res = self.start_game(
            admin_mode="fixed",
            admin_config={"fixed_index": 4},
        )

        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_start_rejects_non_object_json(self):
        res = self.client.post("/api/start", json=[])

        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_round_requires_scores_for_every_player(self):
        res = self.start_game()
        self.assertEqual(res.status_code, 200)

        res = self.client.post("/api/round", json={"scores": {"A": 0}})

        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_round_rejects_boolean_score(self):
        res = self.start_game()
        self.assertEqual(res.status_code, 200)

        res = self.client.post("/api/round", json={"scores": {"A": True, "B": -1}})

        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_manual_admin_round_accepts_complete_scores(self):
        res = self.start_game(admin_mode="manual")
        self.assertEqual(res.status_code, 200)

        res = self.client.post(
            "/api/round",
            json={"admin": "A", "scores": {"A": 5, "B": -5}},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"]["rounds"][0]["admin"], "A")


if __name__ == "__main__":
    unittest.main()
