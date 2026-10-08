import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ui.main_window import MainWindow


class BatchQueueStateTests(unittest.TestCase):
    def make_item(self, state="Pending"):
        return SimpleNamespace(
            job_state=state,
            error_detail="",
            set_status=Mock(),
            set_progress=Mock(),
            status_label=Mock(),
            remove_button=Mock(),
        )

    def test_failed_item_is_marked_and_later_jobs_remain_queued(self):
        failed = self.make_item("Encoding")
        pending = self.make_item()
        window = SimpleNamespace(
            queue_items=[failed, pending],
            current_queue_index=0,
            append_log=Mock(),
            update_batch_status=Mock(),
            start_next_queue_item=Mock(),
        )

        with patch("app.ui.main_window.QTimer.singleShot") as schedule:
            MainWindow._fail_current_queue_item(
                window,
                "FFmpeg exited with code 1",
            )

        self.assertEqual(failed.job_state, "Failed")
        self.assertEqual(failed.error_detail, "FFmpeg exited with code 1")
        failed.set_status.assert_called_once_with("Failed")
        failed.status_label.setToolTip.assert_called_once_with(
            "FFmpeg exited with code 1"
        )
        self.assertEqual(pending.job_state, "Pending")
        self.assertEqual(window.current_queue_index, 1)
        schedule.assert_called_once_with(
            150,
            window.start_next_queue_item,
        )

    def test_cancellation_marks_active_job_and_preserves_pending_jobs(self):
        active = self.make_item("Encoding")
        pending = self.make_item()
        window = SimpleNamespace(
            queue_items=[active, pending],
            current_queue_index=0,
            append_log=Mock(),
            update_batch_status=Mock(),
        )

        MainWindow.current_item_cancelled(window)

        self.assertEqual(active.job_state, "Cancelled")
        self.assertEqual(active.error_detail, "Cancelled by user.")
        active.set_status.assert_called_once_with("Cancelled")
        active.set_progress.assert_called_once_with(0)
        self.assertEqual(pending.job_state, "Pending")

    def test_batch_summary_reports_completed_failed_cancelled_and_pending(self):
        window = SimpleNamespace(
            queue_items=[
                self.make_item("Completed"),
                self.make_item("Failed"),
                self.make_item("Cancelled"),
                self.make_item("Pending"),
                self.make_item("Encoding"),
            ],
            batch_status_label=Mock(),
        )

        MainWindow.update_batch_status(window)

        self.assertEqual(
            window.batch_status_label.setText.call_args.args[0],
            "Completed: 1  ·  Failed: 1  ·  Cancelled: 1  ·  "
            "Pending: 1  ·  Active: 1",
        )


if __name__ == "__main__":
    unittest.main()
