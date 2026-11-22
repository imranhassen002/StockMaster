import tkinter as tk

from stockmaster.app import StockMasterApp


def main():
    root = tk.Tk()
    StockMasterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
