import unittest

from playwright.sync_api import sync_playwright

from senpilot.catalog import locate_document, parse_row
from senpilot.models import RetrievalError


class VirtualGridTests(unittest.TestCase):
    def check_row_update(self, *, active_flag, actual_id="2", animation_frames=True):
        expected = {"201.1": "2", "202.1": "Expected filing", "203.1": "04/07/2025", "204.1": "Public"}
        fields = "".join(f'<div class="fm-textarea" id="b0p1o{key.split(".")[0]}i1i0r1">{value}</div>'
                         for key, value in {**expected, "201.1": "1", "202.1": "Stale filing"}.items())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(1500)
                page.set_content(f"""
                <style>.fm-textarea{{display:inline;font-size:1px;line-height:1px}} td{{padding:0}}</style>
                <div class="v-grid-scroller-vertical" style="height:68px;overflow:auto"><div style="height:136px"></div></div>
                <table style="border-collapse:collapse"><tbody class="v-grid-body">
                  <tr class="v-grid-row" style="height:68px;transform:translate3d(0,0,0)"><td>{fields}<button>GO GET IT</button></td></tr>
                </tbody></table>
                <script>
                  window.updating=false;
                  {'' if animation_frames else 'window.requestAnimationFrame=()=>0;'}
                  window.vaadin={{clients:{{test:{{isActive:()=>window.updating}}}}}};
                  document.querySelector('.v-grid-scroller-vertical').addEventListener('scroll',()=>{{
                    window.updating={str(active_flag).lower()};
                    document.querySelector('tr').style.transform='translate3d(0,68px,0)';
                    setTimeout(()=>{{
                      document.querySelector('#b0p1o201i1i0r1').textContent='{actual_id}';
                      document.querySelector('#b0p1o202i1i0r1').textContent='Expected filing';
                      window.updating=false;
                    }},200);
                  }});
                </script>""")
                document = parse_row("Other Documents", {"position": 1, "fields": expected})
                row = locate_document(page, document)
                self.assertIn("Expected filing", row.inner_text())
                self.assertNotIn("Stale filing", row.inner_text())
            finally:
                browser.close()

    def test_row_position_can_change_before_its_contents(self):
        self.check_row_update(active_flag=True)

    def test_identity_wait_also_handles_pending_layout_after_ui_idle(self):
        self.check_row_update(active_flag=False)

    def test_changed_source_identity_is_rejected(self):
        with self.assertRaises(RetrievalError):
            self.check_row_update(active_flag=False, actual_id="3")

    def test_identity_checks_do_not_depend_on_animation_frame_callbacks(self):
        self.check_row_update(active_flag=False, animation_frames=False)


if __name__ == "__main__":
    unittest.main()
