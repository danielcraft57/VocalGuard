/**
 * Tests page login UI web.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "./page";

const mockLocationReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("next=%2Fdashboard"),
}));

jest.mock("../../services/authUiApi", () => ({
  fetchUiSession: jest.fn().mockResolvedValue({ authenticated: false, ui_password_enabled: true }),
  loginUi: jest.fn(),
}));

import { fetchUiSession, loginUi } from "../../services/authUiApi";

describe("LoginPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { replace: mockLocationReplace },
    });
  });

  it("affiche le formulaire de connexion", async () => {
    render(<LoginPage />);
    expect(await screen.findByLabelText(/Mot de passe/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Se connecter/i })).toBeInTheDocument();
  });

  it("affiche une erreur si le mot de passe est incorrect", async () => {
    (loginUi as jest.Mock).mockRejectedValueOnce(new Error("Mot de passe incorrect."));
    render(<LoginPage />);
    const input = await screen.findByLabelText(/Mot de passe/i);
    await userEvent.type(input, "mauvais");
    await userEvent.click(screen.getByRole("button", { name: /Se connecter/i }));
    expect(await screen.findByText(/Mot de passe incorrect/i)).toBeInTheDocument();
  });

  it("redirige apres connexion reussie", async () => {
    (loginUi as jest.Mock).mockResolvedValueOnce(undefined);
    render(<LoginPage />);
    const input = await screen.findByLabelText(/Mot de passe/i);
    await userEvent.type(input, "secret");
    await userEvent.click(screen.getByRole("button", { name: /Se connecter/i }));
    await waitFor(() => {
      expect(mockLocationReplace).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("redirige si mot de passe UI desactive", async () => {
    (fetchUiSession as jest.Mock).mockResolvedValueOnce({ authenticated: true, ui_password_enabled: false });
    render(<LoginPage />);
    await waitFor(() => {
      expect(mockLocationReplace).toHaveBeenCalledWith("/dashboard");
    });
  });
});
