"""GUI smoke test (offscreen): load, change a slider, focus a result, render all charts."""

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # keep the user's GUI settings untouched
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from .conftest import LEGAL, PERSONAL  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window(app, tmp_path):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    app.processEvents()
    assert w.res is not None and w.results.focus_id == "saldo"
    saldo0 = w.res.saldo

    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    ctrl.spin.setValue(ctrl.spin.value() + 50_000)
    w.recalc()
    assert w.res.saldo != saldo0
    assert w.s.origin_of("persons.0.severance") == "angabe"  # editing keeps the origin from the XML

    # exactly one focused value; the explanation follows the focus
    w.results.set_focus("est_2027")
    assert w.results.focus_id == "est_2027"
    assert "Einkommensteuer 2027" in w.explain.view.toPlainText()
    focused = [i for i in w.results.items.values() if i.text(0).startswith("▶ ")]
    assert len(focused) == 1
    w.results.set_focus("saldo")
    assert "Netto-Saldo" in w.explain.view.toPlainText()

    for i in range(w.charts.tabs.count()):
        w.charts.tabs.setCurrentIndex(i)
        app.processEvents()

    out = tmp_path / "p.xml"
    assert w._write(str(out), backup=False)
    from abfindung.io import load_personal
    assert load_personal(out).persons[0].abfindung.value == w.s.persons[0].severance
    w.dirty = False
    w.close()


def test_section_checkbox_greys_out(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    app.processEvents()
    assert w.inputs.tabs.tabText(0) == "Steuerpflichtige(r)"
    assert w.inputs.tabs.tabText(1) == "Ehepartner"
    assert "partner" not in w.inputs.sections and len(w.inputs.sections) == 4
    check, content, _ = w.inputs.sections["gestaltungen"]
    check.setChecked(False)
    w.recalc()
    assert not content.isEnabled() and not w.s.active("gestaltungen")
    check.setChecked(True)
    assert content.isEnabled()
    w.dirty = False
    w.close()


def test_salary_years_after_exit_greyed(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    rows = {y: (ctrl, info) for y, ctrl, info in w.inputs.salary_rows[1]}
    assert not rows[2028][0].isEnabled() and "nicht relevant" in rows[2028][1].text()
    assert rows[2027][0].isEnabled() and "anteilig bis Austritt" in rows[2027][1].text()
    w.dirty = False
    w.close()


def test_real_salary_shows_annual_equivalent(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    mode = next(c for c in w.inputs.controls if c.path == "persons.1.salary_mode")
    mode.combo.setCurrentIndex(1)
    rows = {y: info for y, _, info in w.inputs.salary_rows[1]}
    assert "hochgerechnet" in rows[2027].text() and "§ 158" in rows[2027].toolTip()
    assert "Steuer- oder Rechtsberatung" in w.disclaimer.text()
    w.dirty = False
    w.close()


def _wheel(widget, ctrl: bool, down: bool = False):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120 if down else 120), Qt.MouseButton.NoButton, mods,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_wheel_needs_ctrl(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    bar = w.inputs.tabs.widget(0).verticalScrollBar()
    before = ctrl.spin.value()
    _wheel(ctrl.spin, ctrl=False, down=True)
    _wheel(ctrl.slider, ctrl=False, down=True)
    assert ctrl.spin.value() == before and w.s.persons[0].severance == before
    assert bar.value() > 0  # the panel scrolled instead
    _wheel(ctrl.spin, ctrl=True)
    assert ctrl.spin.value() == before + ctrl.spin.singleStep()  # exactly one normal step
    w.dirty = False
    w.close()


def test_notice_period_derived_greys_out_manual_value(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    frist = next(c for c in w.inputs.controls if c.path == "persons.0.kfrist_monate")
    bz = next(c for c in w.inputs.controls if c.path == "persons.0.bz_jahre")
    assert frist.spin.isEnabled()
    w.inputs.set_origin("persons.0.kfrist_monate", "abgeleitet")
    w.recalc()
    assert not frist.spin.isEnabled() and bz.isEnabled()
    assert "T_Kuendigungsfristen_AG" in frist.toolTip()
    w.dirty = False
    w.close()


def test_recalc_waits_until_spin_arrow_released(app):
    """Clicking a spin box arrow must step exactly once: no recalculation while the button is held."""
    import time

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle, QStyleOptionSpinBox

    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    sp = next(c for c in w.inputs.controls if c.path == "persons.0.severance").spin
    w.inputs.tabs.widget(0).ensureWidgetVisible(sp)
    app.processEvents()
    opt = QStyleOptionSpinBox()
    sp.initStyleOption(opt)
    up = app.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, sp).center()
    calls = []
    original = w.recalc
    w.recalc = lambda: (calls.append(1), original())
    v0 = sp.value()
    QTest.mousePress(sp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, up)
    end = time.perf_counter() + 0.35
    while time.perf_counter() < end:
        app.processEvents()
    assert not calls  # held: no recalculation yet
    QTest.mouseRelease(sp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, up)
    end = time.perf_counter() + 0.6
    while time.perf_counter() < end and not calls:
        app.processEvents()
    assert calls and sp.value() == v0 + sp.singleStep()
    w.dirty = False
    w.close()


def test_origin_badge(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.pay_idx")
    w.inputs.set_origin("persons.0.pay_idx", "angabe")
    assert "Angabe" in ctrl.badge.text() and w.s.origin_of("persons.0.pay_idx") == "angabe"
    w.dirty = False
    w.close()


def test_change_markers_reset_and_save(app, tmp_path):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    assert not ctrl.dot.text() and not w.inputs.has_changes() and not w.dirty
    v0 = ctrl.spin.value()
    ctrl.spin.setValue(v0 + 10_000)
    assert ctrl.dot.text() == "●" and "gespeichert: 150.000 €" in ctrl.dot.toolTip()
    assert not ctrl.odot.text()
    assert not w.inputs.tabs.tabIcon(0).isNull() and w.inputs.tabs.tabIcon(1).isNull() and w.dirty
    rows = w.inputs.changes()
    assert len(rows) == 1 and rows[0][0] == "persons.0.severance"

    # back to the saved value by hand: no longer marked
    ctrl.spin.setValue(v0)
    assert not ctrl.dot.text() and not w.dirty

    # origin change: marker + dashed badge; Ctrl+click on the marker resets value and origin
    ctrl.spin.setValue(v0 + 5_000)
    w.inputs.set_origin("persons.0.severance", "annahme")
    assert ctrl.odot.text() == "●" and "gespeichert: Angabe" in ctrl.odot.toolTip()
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(2, 2), QPointF(2, 2), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
    ctrl.odot.mousePressEvent(ev)  # resets only the origin
    assert w.s.origin_of("persons.0.severance") == "angabe" and w.s.persons[0].severance == v0 + 5_000
    assert not ctrl.odot.text() and ctrl.dot.text()
    ctrl.dot.mousePressEvent(ev)  # resets the value
    assert w.s.persons[0].severance == v0 and not ctrl.dot.text()

    # saving makes the current state the new reference
    ctrl.spin.setValue(v0 + 1_000)
    assert w._write(str(tmp_path / "p.xml"), backup=False)
    assert not ctrl.dot.text() and not w.dirty
    w.close()


def test_undo_redo(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    assert not w.a_undo.isEnabled() and not w.a_redo.isEnabled()
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    v0 = ctrl.spin.value()
    # several changes in quick succession form one step
    for k in range(1, 4):
        ctrl.spin.setValue(v0 + k * 1000)
    w._end_group()
    w.inputs.set_origin("persons.0.severance", "annahme")
    w._end_group()
    assert len(w.undo_stack) == 2 and w.a_undo.isEnabled()

    w.undo()  # origin back
    assert w.s.origin_of("persons.0.severance") == "angabe" and w.s.persons[0].severance == v0 + 3000
    w.undo()  # value back
    assert w.s.persons[0].severance == v0 and not w.dirty
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")  # rebuilt
    assert ctrl.spin.value() == v0 and not ctrl.dot.text()
    assert not w.a_undo.isEnabled() and w.a_redo.isEnabled()

    w.redo()
    assert w.s.persons[0].severance == v0 + 3000 and w.dirty
    # a new change after undo discards the redo history
    w.undo()
    ctrl = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    ctrl.spin.setValue(v0 + 500)
    assert not w.redo_stack
    w.dirty = False
    w.close()


def test_ctrl_click_on_origin_badge_resets_origin(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    w.show()
    c = next(c for c in w.inputs.controls if c.path == "persons.0.severance")
    w.inputs.set_origin("persons.0.severance", "annahme")
    QTest.mouseClick(c.badge, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, c.badge.rect().center())
    assert w.s.origin_of("persons.0.severance") == "angabe" and not c.odot.text()
    w.dirty = False
    w.close()


def test_fifth_rule_derived_by_program(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    c = next(c for c in w.inputs.controls if c.path == "persons.0.fuenftel_ok")
    assert c.check.isEnabled()
    w.inputs.set_origin("persons.0.fuenftel_ok", "abgeleitet")
    w.recalc()
    assert not c.check.isEnabled() and "Vom Programm abgeleitet" in c.toolTip()
    assert c.check.isChecked() == w.res.rs["zusammenballung_P_Erika"].value
    assert c.badge.isEnabled()  # the origin can still be changed back
    w.inputs.set_origin("persons.0.fuenftel_ok", "angabe")
    w.recalc()
    assert c.check.isEnabled() and "Vom Programm abgeleitet" not in c.toolTip()
    w.dirty = False
    w.close()


def test_children_list_edit_add_remove_and_save(app, tmp_path):
    from abfindung.engine.settings import from_personal
    from abfindung.gui.main_window import MainWindow
    from abfindung.io import load_legal, load_personal

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    c = next(c for c in w.inputs.controls if c.path == "children")
    assert w.inputs.s.children == [(2015, True), (2019, True)] and len(c.rows) == 2
    c.rows[1][1].setValue(2020)
    c.rows[0][2].setChecked(False)
    assert w.inputs.s.children == [(2015, False), (2020, True)]
    assert c.dot.text() and any(ch[0] == "children" for ch in w.inputs.changes())
    c.add_btn.click()
    assert len(w.inputs.s.children) == 3 and len(c.rows) == 3
    c.rows[0][3].click()  # remove the first child
    assert w.inputs.s.children[0] == (2020, True) and len(w.inputs.s.children) == 2
    w.recalc()
    out = tmp_path / "p.xml"
    assert w._write(str(out), backup=False)
    s2 = from_personal(load_personal(out), load_legal(LEGAL))
    assert s2.children == w.inputs.s.children
    ids = [k.id for k in load_personal(out).household.kinder]
    assert len(set(ids)) == 2
    assert not c.dot.text()
    saved = list(w.inputs.s.children)
    w._end_group()
    c.add_btn.click()
    w._end_group()
    w.undo()
    assert w.inputs.s.children == saved and len(c.rows) == 2
    w.dirty = False
    w.close()


def test_marital_status_shows_or_hides_spouse_tab(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    titles = lambda: [w.inputs.tabs.tabText(i).lstrip("● ") for i in range(w.inputs.tabs.count())]  # noqa: E731
    assert "Ehepartner" in titles()
    fam = next(c for c in w.inputs.controls if c.path == "familienstand")
    fam.combo.setCurrentIndex([v for v, _ in fam.options].index("ledig"))
    assert w.s.familienstand == "ledig" and "Ehepartner" not in titles()
    w.recalc()
    assert list(w.res.ctx.timelines) == ["P_Erika"]
    assert any(ch[0] == "familienstand" for ch in w.inputs.changes())
    w.inputs.reset_value("familienstand")
    assert w.s.married and "Ehepartner" in titles()
    w.dirty = False
    w.close()


def test_gestaltungen_add_remove_undo_and_save(app, tmp_path):
    from abfindung.engine.settings import from_personal
    from abfindung.gui.main_window import MainWindow
    from abfindung.io import load_legal, load_personal

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    p = w.inputs
    p.add_typ.setCurrentIndex(p.add_typ.findData("sonstige"))
    p.add_year.setValue(2027)
    p.add_gestaltung(p.add_typ.currentData(), p.add_year.value())
    gid = next(iter(w.s.measures.items))
    assert gid in p.item_boxes and any(ch[0] == "gestaltungen" for ch in p.changes())
    name = next(c for c in p.controls if c.path == f"measures.items.{gid}.name")
    name.edit.setText("Fortbildung")
    name.edit.editingFinished.emit()
    assert p.item_boxes[gid].title() == "Fortbildung 2027"
    p.add_gestaltung("spende", 2027)
    p.add_gestaltung("spende", 2027)
    assert len(w.s.measures.items) == 3
    w.recalc()
    out = tmp_path / "p.xml"
    assert w._write(str(out), backup=False)
    s2 = from_personal(load_personal(out), load_legal(LEGAL))
    assert sorted(g.typ for g in s2.measures.items.values()) == ["sonstige", "spende", "spende"]
    assert not p.changes()
    w._end_group()
    p.remove_gestaltung(gid)
    w._end_group()
    assert gid not in w.s.measures.items and gid not in p.item_boxes
    w.undo()
    assert gid in w.s.measures.items and gid in w.inputs.item_boxes
    w.dirty = False
    w.close()


def test_elstam_in_options_tab(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    tab = next(t for t, paths in zip(w.inputs.tab_titles, w.inputs.tab_paths) if "options.lst_freibetrag" in paths)
    assert tab == "Optionen"
    w.dirty = False
    w.close()


def test_no_exit_greys_out_exit_inputs(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    c = {x.path: x for x in w.inputs.controls}
    sw = c["persons.1.austritt"]
    assert sw.check.isChecked() and c["persons.1.end_date"].isEnabled()
    sw.check.setChecked(False)
    for path in ("persons.1.end_date", "persons.1.severance", "persons.1.meldung"):
        assert not c[path].parentWidget().isEnabled(), path
    assert c["persons.1.salary.2027"].isEnabled()  # no exit: the salary of later years counts
    w.recalc()
    assert w.res.ctx.timelines["P_Max"].alg_end is None
    assert any("kein Austritt" in t for t, _ in w.res.warnings)
    w.dirty = False
    w.close()


def test_tabs_fit_a_narrow_panel(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    for typ in ("basisrente", "erhaltung", "spende", "kauf", "sonstige"):
        w.inputs.add_gestaltung(typ, 2027)
    tabs = w.inputs.tabs
    widths = {tabs.tabText(i): tabs.widget(i).widget().minimumSizeHint().width() for i in range(tabs.count())}
    others = max(v for k, v in widths.items() if "Gestaltungen" not in k)  # font-independent: no tab wider than the rest
    assert max(widths.values()) <= others + 20, widths
    w.dirty = False
    w.close()


def test_alg_switch_greys_out_alg_inputs(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    c = {x.path: x for x in w.inputs.controls}
    assert c["persons.0.alg_aktiv"].parentWidget().title() == "Arbeitslosengeld"
    c["persons.0.alg_aktiv"].check.setChecked(False)
    for path in ("persons.0.meldung", "persons.0.sperrzeit_wochen", "persons.0.alg_monat"):
        assert not c[path].parentWidget().isEnabled(), path
    w.dirty = False
    w.close()


def test_kv_switch_greys_out_kv_inputs(app):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    c = {x.path: x for x in w.inputs.controls}
    assert c["persons.0.kv_aktiv"].parentWidget().title() == "Krankenversicherung"
    c["persons.0.kv_aktiv"].check.setChecked(False)
    for path in ("persons.0.kv_status", "persons.0.kv_beitrag_schaetzung", "persons.0.kv_sonstige_einnahmen"):
        assert not c[path].parentWidget().isEnabled(), path
    w.recalc()
    assert not w.res.ctx.kv["P_Erika"].months
    w.dirty = False
    w.close()


def test_first_start_uses_the_empty_template(app, tmp_path, monkeypatch):
    from abfindung.gui.main_window import MainWindow

    w = MainWindow(None, str(LEGAL), dark=False)
    w.qs.remove("personal_path")
    w._load_initial(None, str(LEGAL))
    assert w.personal_path is None and w.s.persons[0].id == "P1" and not w.s.married
    assert "neu" in w.windowTitle()
    target = tmp_path / "neu.xml"
    assert w._write(str(target), backup=False) and target.exists()
    w.dirty = False
    w.close()


def test_recent_personal_files_and_no_toolbar(app, tmp_path):
    from PySide6.QtWidgets import QToolBar

    from abfindung.gui.main_window import MainWindow

    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    w.qs.remove("recent_personal")
    copy = tmp_path / "kopie.xml"
    assert w._write(str(copy), backup=False)  # saving remembers the file
    w._load(str(PERSONAL), None)
    assert w.recent_files()[:2] == [str(PERSONAL.resolve()), str(copy.resolve())]
    w._fill_recent_menu()
    texts = [a.text() for a in w.recent_menu.actions()]
    assert texts[0] == "&1 beispiel_persoenlich.xml" and "Liste leeren" in texts
    w.open_recent(str(copy))
    assert w.personal_path == str(copy) and w.recent_files()[0] == str(copy.resolve())
    assert not w.findChildren(QToolBar)
    w.dirty = False
    w.close()


def test_german_texts_for_qt_buttons(app):
    from PySide6.QtWidgets import QDialogButtonBox

    from abfindung.__main__ import install_german_translation

    assert install_german_translation(app)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Cancel)
    texts = {b.text().replace("&", "") for b in box.buttons()}
    assert {"Schließen", "Abbrechen"} <= texts
