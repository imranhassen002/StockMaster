from tkinter import ttk


def configure_styles(root):
    """Define the shared colors and typography for the application."""
    style = ttk.Style(root)
    style.theme_use("clam")

    navy = "#14233D"
    background = "#F1F4F8"
    white = "#FFFFFF"
    text = "#18263D"
    muted = "#52627A"
    blue = "#245CC7"
    font = "Segoe UI"

    style.configure("TFrame", background=background)
    style.configure("TLabel", background=background, foreground=text, font=(font, 11))
    style.configure("Sidebar.TFrame", background=navy)
    style.configure("Surface.TFrame", background=white)
    style.configure(
        "Card.TFrame", background=white, bordercolor="#DCE4EF",
        borderwidth=1, relief="solid",
    )
    style.configure(
        "Brand.TLabel", background=navy, foreground=white, font=(font, 19, "bold")
    )
    style.configure(
        "PageTitle.TLabel", background=white, foreground=text, font=(font, 24, "bold")
    )
    style.configure("Subtitle.TLabel", background=white, foreground=muted)
    style.configure("SectionTitle.TLabel", font=(font, 16, "bold"))
    style.configure("CardLabel.TLabel", background=white, foreground=muted)
    style.configure(
        "CardValue.TLabel", background=white, foreground=text, font=(font, 24, "bold")
    )
    style.configure(
        "Primary.TButton", background=blue, foreground=white, bordercolor=blue,
        lightcolor=blue, darkcolor=blue, focuscolor="#BBD4FF", padding=(10, 5),
    )
    style.map("Primary.TButton", background=[("pressed", "#1B4696"), ("active", "#2D6ADA")])
    style.configure("Treeview", background=white, fieldbackground=white,
                    foreground=text, font=(font, 10), rowheight=30)
    style.configure("Muted.TLabel", foreground=muted, font=(font, 10))
    style.configure(
        "Treeview.Heading", font=(font, 10, "bold"), padding=(6, 7),
        background=navy, foreground=white, relief="flat", bordercolor=navy,
    )
    style.map("Treeview.Heading", background=[("active", "#233B60")])
    style.map("Treeview", background=[("selected", blue)], foreground=[("selected", white)])

    style.configure(
        "Navigation.TButton", background=navy, foreground=white,
        bordercolor=navy, lightcolor=navy, darkcolor=navy, focuscolor="#BBD4FF",
        padding=(12, 10), anchor="w", font=(font, 11, "bold"),
    )
    style.map(
        "Navigation.TButton",
        background=[("pressed", "#1B4696"), ("selected", blue), ("active", "#233B60")],
        bordercolor=[("selected", blue), ("active", "#233B60")],
        lightcolor=[("selected", blue), ("active", "#233B60")],
        darkcolor=[("selected", blue), ("active", "#233B60")],
    )
