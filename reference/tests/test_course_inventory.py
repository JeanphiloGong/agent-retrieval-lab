import unittest
from pathlib import Path

from labs.verify_course import verify


class CourseInventoryTests(unittest.TestCase):
    def test_all_planned_checkpoints_have_reference_artifacts(self):
        self.assertEqual(verify(Path(__file__).parents[2]), {"topics": 9, "versions": 37, "tutorials": 37})


if __name__ == "__main__":
    unittest.main()
