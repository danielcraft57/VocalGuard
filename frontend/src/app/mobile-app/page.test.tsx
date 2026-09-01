/**
 * Tests page appairage mobile QR.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MobileAppPage from "./page";

jest.mock("../../components/AppLayout", () => ({
  AppLayout: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

jest.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value }: { value: string }) => <div data-testid="qr-mock">{value}</div>,
}));

jest.mock("../../services/publicApiAdmin", () => ({
  listPublicTokens: jest.fn().mockResolvedValue([{ id: 1, name: "Mobile", is_active: true }]),
  revealPublicToken: jest.fn().mockResolvedValue({ token: "bearer-test" }),
}));

jest.mock("../../services/mobilePairingApi", () => ({
  createPairingSession: jest.fn().mockResolvedValue({
    pairing_id: 1,
    code: "AB12CD34",
    expires_at: new Date(Date.now() + 300000).toISOString(),
    qr_uri: "vocalguard://pair?v=1&host=https://test&code=AB12CD34",
  }),
  testMobilePing: jest.fn().mockResolvedValue({
    ok: true,
    api_ok: true,
    ws_ok: true,
    modem_ok: false,
  }),
}));

import { createPairingSession, testMobilePing } from "../../services/mobilePairingApi";

describe("MobileAppPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.assign(navigator, {
      clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
    });
  });

  it("genere un QR code au clic sans champ URL", async () => {
    render(<MobileAppPage />);
    expect(screen.queryByLabelText(/URL/i)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Generer le QR code/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("button", { name: /Generer le QR code/i }));
    expect(createPairingSession).toHaveBeenCalledWith(
      expect.objectContaining({
        create_token_if_missing: true,
        base_url: expect.any(String),
      }),
    );
    expect(await screen.findByTestId("qr-mock")).toHaveTextContent("vocalguard://pair");
    expect(screen.getByText("AB12CD34")).toBeInTheDocument();
  });

  it("lance le test ping serveur", async () => {
    render(<MobileAppPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Tester la connexion/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("button", { name: /Tester la connexion/i }));
    await waitFor(() => {
      expect(testMobilePing).toHaveBeenCalledWith("bearer-test");
    });
    expect(await screen.findByText("API")).toBeInTheDocument();
  });
});
