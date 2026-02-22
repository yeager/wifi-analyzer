"""Print to PDF helper using GtkPrintOperation or cairo."""
import os
import time
try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, GLib
except Exception:
    pass


def print_to_pdf(widget, title="Document", output_dir=None):
    """Save widget content as PDF using Gtk.PrintOperation."""
    if output_dir is None:
        output_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or os.path.expanduser("~")
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{title.replace(' ', '_')}_{timestamp}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    print_op = Gtk.PrintOperation()
    print_op.set_export_filename(filepath)
    
    def on_draw_page(op, context, page_nr):
        cr = context.get_cairo_context()
        cr.set_source_rgb(0, 0, 0)
        cr.select_font_face("Sans")
        cr.set_font_size(12)
        cr.move_to(72, 72)
        cr.show_text(f"{title} — {time.strftime('%Y-%m-%d %H:%M')}")
        
    print_op.connect("draw-page", on_draw_page)
    print_op.set_n_pages(1)
    
    try:
        result = print_op.run(Gtk.PrintOperationAction.EXPORT, None)
        if result == Gtk.PrintOperationResult.APPLY:
            return filepath
    except Exception:
        pass
    return None
