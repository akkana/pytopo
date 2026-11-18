#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from pytopo import MapUtils


prompt_dialog = None

def prompt(prompt, comment="", name="", show_delete=False):
    """Prompt the user for a string, returning the string.
       Returns None if the user presses CANCEL instead
       (as opposed to an empty string, which means the
       user didn't type anything but hit OK).
       If show_delete is True, also show a Delete toggle button,
       and return a tuple where the second item is the state of the button.
    """
    global prompt_dialog

    if not prompt_dialog:
        prompt_dialog = Gtk.Dialog("PyTopo: %s" % prompt, None, 0,
                                        (Gtk.STOCK_CANCEL,
                                           Gtk.ResponseType.CANCEL,
                                         Gtk.STOCK_OK,
                                           Gtk.ResponseType.OK))
        prompt_dialog.set_size_request(200, 150)
        prompt_dialog.vbox.set_spacing(10)

        prompt_dialog_prompt = Gtk.Label(prompt)
        prompt_dialog.vbox.pack_start(prompt_dialog_prompt,
                                      False, True, 0)

        prompt_dialog_del_btn = Gtk.ToggleButton("Delete")
        prompt_dialog.vbox.pack_start(prompt_dialog_del_btn,
                                      False, True, 0)

        prompt_dialog_text = Gtk.Entry()
        prompt_dialog_text.set_activates_default(True)
        prompt_dialog.vbox.pack_start(prompt_dialog_text,
                                      True, True, 0)

        prompt_dialog_comment = Gtk.Label("")
        prompt_dialog.vbox.pack_start(prompt_dialog_comment,
                                      False, True, 0)

        prompt_dialog.show_all()

    else:
        prompt_dialog_comment.set_text(comment)
        prompt_dialog_prompt.set_text(prompt)

    prompt_dialog_del_btn.set_active(False)

    if show_delete:
        prompt_dialog_del_btn.show()
    else:
        prompt_dialog_del_btn.hide()

    prompt_dialog.set_default_response(Gtk.ResponseType.OK)
    prompt_dialog_text.set_text(name)
    if name:
        prompt_dialog_text.select_region(0, len(name))
    prompt_dialog_text.grab_focus()
    prompt_dialog.show()

    response = prompt_dialog.run()
    if response == Gtk.ResponseType.OK:
        prompt_dialog.hide()
        retval = prompt_dialog_text.get_text()
    else:
        prompt_dialog.hide()
        retval = None

    if show_delete:
        return retval, prompt_dialog_del_btn.get_active()
    else:
        return retval


def known_site_chooser(known_sites):
    """
       Prompt with the list of known sites and an entry for coordinates.
       Returns lat, lon,
       or a list of name, lon, lat, collectionname, zoom,
       or None
    """
    dialog = Gtk.Dialog("Choose a starting point",
                        transient_for=None, flags=0)
    dialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)

    # dialog.connect('destroy', lambda win: Gtk.main_quit())
    # Wouldn't it be nice if GTK dialogs would automatically
    # size to their contents? Sigh. Without this, the dialog
    # is wide enough for the text box but includes none of the
    # site list in the scrolled window below it.
    dialog.set_size_request(600, 400)

    sw = Gtk.ScrolledWindow()
    sw.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

    svbox = Gtk.VBox(spacing=10)

    hbox = Gtk.HBox(spacing=6)
    svbox.pack_start(hbox, False, True, 0)

    hbox.pack_start(Gtk.Label(label="Coordinates:"), False, True, 0)

    # An entry to enter specific coordinates
    coord_entry = Gtk.Entry()
    coord_entry.set_width_chars(45)
    coord_entry.set_activates_default(True)
    hbox.pack_start(coord_entry, False, True, 0)
    dialog.coord_entry = coord_entry

    # make OK button the default, so Enter in the entry will trigger OK
    okButton = dialog.get_widget_for_response(
        response_id=Gtk.ResponseType.OK)
    okButton.set_can_default(True)
    okButton.grab_default()

    # List store will hold name, collection-name and site object
    store = Gtk.ListStore(str, str, object)

    # Create the list
    print("known sites:", known_sites)
    for site in known_sites:
        if len(site) > 3:
            coll = site[3]
        else:
            coll = ''
        store.append([site[0], coll, site])

    # http://pyGtk.org/pyGtk2tutorial/ch-TreeViewWidget.html
    # Make a treeview from the list:
    treeview = Gtk.TreeView(model=store)

    renderer = Gtk.CellRendererText()
    column = Gtk.TreeViewColumn("Location", renderer, text=0)
    # column.pack_start(renderer, True, True, True, 0)
    # column.set_resizable(True)
    treeview.append_column(column)
    renderer = Gtk.CellRendererText()
    column = Gtk.TreeViewColumn("Collection", renderer, text=1)
    # column.pack_start(renderer, False, True, 0)
    treeview.append_column(column)

    # store.set_sort_column_id(0, Gtk.SORT_ASCENDING)

    # Catch middle-mouse pastes over the treeview
    treeview.connect("button-release-event", accept_paste)

    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    svbox.pack_start(treeview, True, True, 0)
    # sw.add(treeview)

    sw.add(svbox)

    # Weirdly, when this was in MapWindowGTK the arguments were value, widget
    # but now that it's in a separate file, there are three args,
    # which seem to be treeview, rownumber, Gtk.TreeViewColumn object
    # fortunately we don't actually use the args here anyway
    def submit(treeview, rownum, column):
        # Tell the dialog to give an OK response
        dialog.response(Gtk.ResponseType.OK)

    treeview.connect("row-activated", submit)
    # treeview.connect("key-pressed", submit)

    dialog.vbox.pack_start(sw, True, True, 0)

    dialog.show_all()

    while True:
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            coordtext = coord_entry.get_text()
            if coordtext:
                try:
                    lat, lon = MapUtils.parse_full_coords(
                        coord_entry.get_text())
                except Exception as e:
                    print("Oops", e)
                    continue
                dialog.destroy()
                return lat, lon

            selection = treeview.get_selection()
            print("selection is", selection)
            model, it = selection.get_selected()   # ListStore, TreeIter
            print("model, it:", model, it)
            if it:
                # locname = store.get_value(it, 0)
                # collname = store.get_value(it, 1)
                site = store.get_value(it, 2)
                #     This should be something  like
                #     [ name, lon, lat, collectionname, zoom ]
                print("value(it, 2) =", site)
                dialog.destroy()
                return site

        else:    # Cancel
            dialog.destroy()
            return None


def accept_paste(widget, event):
    """Handle middlemouse pastes over the site selection dialog.
       Ideally this would actually submit the dialog and open up
       the MapWindow.
    """
    if event.button != 2:
        return False

    dialog = widget.get_toplevel()

    # clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    selection = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
    coordstr = selection.wait_for_text()

    dialog.coord_entry.set_text(coordstr)

    '''
    # Now that the dialog's entry is filled, the goal is to
    # submit the dialog. But I haven't found any way to do that.
    # Sending a fake enter key event from the entry doesn't do it,
    # nor does sending a button press event on the dialog's OK button.
    # Better would be to send the "clicked" signal to the button,
    # but there doesn't seem to be a way to manually generate signals.
    print("Trying to send event ...")

    event = Gdk.Event(Gdk.EventType.KEY_PRESS)
    event.window = dialog.coord_entry.get_window()
    display = Gdk.Display().get_default()
    keymap = Gdk.Keymap().get_for_display(display)
    key = keymap.get_entries_for_keyval(Gdk.KEY_Return)
    event.hardware_keycode = key[1][0].keycode
    event.send_event = True
    event = Gdk.Event(Gdk.EventType.KEY_RELEASE)
    dialog.coord_entry.emit('key-release-event', event)

    ok_button = dialog.get_widget_for_response(
        response_id=Gtk.ResponseType.OK)
    event = Gdk.Event(Gdk.EventType.BUTTON_PRESS)
    event.window = dialog.get_window()
    event.button = 1
    event.send_event = True
    ok_button.emit('button-press-event', event)
    event = Gdk.Event(Gdk.EventType.BUTTON_RELEASE)
    event.window = dialog.get_window()
    event.button = 1
    event.send_event = True
    ok_button.emit('button-release-event', event)
    '''

    return True


def ignorecasefilter(filter_info, data):
    """A GTK GtkFileFilter function that filters for
       a given set of extensions IGNORING CASE,
       which GTK, incredibly, does not offer in Gtk.FileFilter.
       The closest to documentation I could find is at
       http://www.manpagez.com/html/pyGtk/pyGtk-2.22.0/class-Gtkfilefilter.php#method-Gtkfilefilter--add-custom

       Arguments:
       data is a list of LOWERCASE file extensions,
           e.g. [".jpg", ".png"].
           Pass it in as the third argument of filter.add_custom.
       filter_info is a Gtk.FileFilterInfo object passed by the
           FileFilter -- not the 4-tuple described on the manpagez link.
           It has four parts, typically
               filter_info.filename      full pathname of the file
               filter_info.url           None
               filter_info.display_name  basename of the file
               filter_info.mime_type
           I don't know when url and mime_type might get set;
           they never have been in my tests.
    """
    for file_ext in data:
        if filter_info.display_name.lower().endswith(file_ext):
            return True
    return False


file_read_folder = None

def prompt_for_file(title=None, filter_name=None, filter_exts=None):
    global file_read_folder

    dialog = Gtk.FileChooserDialog(title=title,
                           action=Gtk.FileChooserAction.SAVE,
                           buttons=(Gtk.STOCK_CANCEL,
                                    Gtk.ResponseType.CANCEL,
                                    Gtk.STOCK_SAVE,
                                    Gtk.ResponseType.OK))
    if file_read_folder:
        dialog.set_current_folder(file_read_folder)

    if filter_exts:
        filt = Gtk.FileFilter()
        if filter_name:
            filt.set_name(filter_name)
        filt.add_custom(Gtk.FileFilterFlags.FILENAME,
                        ignorecasefilter, filter_exts)
        dialog.add_filter(filt)

    response = dialog.run()

    if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return None

    file_read_folder = dialog.get_current_folder()
    infile = dialog.get_filename()
    dialog.destroy()
    return infile


def chart_chooser_dialog(keys_available):
    """Let the user choose which charts they want to see.
       Return keys_chosen.
    """
    dialog = Gtk.Dialog("Choose a starting point",
                        transient_for=None, flags=0)
    dialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)

    dialog.vbox.pack_start(Gtk.Label("Show charts:"), False, True, 0)
    buttons = []
    for key in keys_available:
        buttons.append(Gtk.CheckButton(label=key))
        dialog.vbox.pack_start(buttons[-1], False, True, 0)
    dialog.show_all()

    response = dialog.run()
    ret = []
    if response == Gtk.ResponseType.OK:
        for button in buttons:
            if button.get_active():
                ret.append(button.get_label())
    else:
        ret = None

    dialog.destroy()
    return ret


if __name__ == '__main__':
    pass

