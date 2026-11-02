"""Smoke-test app.py without Streamlit installed: a stub `streamlit` module returns each
widget's default value and renders every Styler, so the full script path executes.
Usage:  python tests/smoke_app.py solar|general
"""
import os
import runpy
import sys
import types

import pandas as pd

MODE = sys.argv[1] if len(sys.argv) > 1 else "solar"
calls = {"charts": 0, "frames": 0, "metrics": 0, "downloads": 0}


class Stop(Exception):
    pass


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(st, name)


def _render(obj):
    if hasattr(obj, "to_html"):
        obj.to_html()  # forces formatters to run
    calls["frames"] += 1


st = types.ModuleType("streamlit")
st.set_page_config = lambda **k: None
st.title = st.subheader = st.caption = st.markdown = lambda *a, **k: None
st.info = st.warning = st.success = lambda *a, **k: None
st.error = lambda *a, **k: (_ for _ in ()).throw(AssertionError(f"st.error: {a}"))


def stop():
    raise Stop()


st.stop = stop
st.radio = lambda label, options, **k: options[0] if MODE == "solar" else options[1]
st.number_input = lambda label, mn=None, mx=None, value=None, step=None, **k: value
st.text_input = lambda label, value="", **k: value
st.checkbox = lambda label, value=False, **k: value
st.selectbox = lambda label, options, index=0, **k: options[index]
st.slider = lambda label, mn, mx, value=None, step=None, **k: value
st.file_uploader = lambda *a, **k: None
st.data_editor = lambda df, **k: df.copy()
st.dataframe = lambda obj, **k: _render(obj)
st.bar_chart = st.line_chart = lambda df, **k: calls.__setitem__("charts", calls["charts"] + 1)
st.metric = lambda *a, **k: calls.__setitem__("metrics", calls["metrics"] + 1)


def download_button(label, data, *a, **k):
    assert data and len(data) > 100, "empty download"
    calls["downloads"] += 1


st.download_button = download_button
st.expander = lambda *a, **k: Ctx()
st.columns = lambda n, **k: [Ctx() for _ in range(n if isinstance(n, int) else len(n))]
st.tabs = lambda names: [Ctx() for _ in names]
st.sidebar = Ctx()
cc = types.SimpleNamespace(SelectboxColumn=lambda *a, **k: None, CheckboxColumn=lambda *a, **k: None,
                           NumberColumn=lambda *a, **k: None)
st.column_config = cc
sys.modules["streamlit"] = st

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)
try:
    runpy.run_path(os.path.join(root, "app.py"), run_name="__main__")
except Stop:
    print("st.stop() reached")
print(MODE, calls)
assert calls["charts"] >= 4 and calls["frames"] >= 3 and calls["downloads"] == 2, calls
print("SMOKE TEST PASSED")
