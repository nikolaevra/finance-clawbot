import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeIntegration } from "@/test/test-utils";

const mocks = vi.hoisted(() => ({
  fetchIntegrations: vi.fn(),
  createLinkToken: vi.fn(),
  createIntegration: vi.fn(),
  deleteIntegration: vi.fn(),
  connectFloat: vi.fn(),
  getGmailAuthUrl: vi.fn(),
  openMergeLink: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  fetchIntegrations: mocks.fetchIntegrations,
  createLinkToken: mocks.createLinkToken,
  createIntegration: mocks.createIntegration,
  deleteIntegration: mocks.deleteIntegration,
  connectFloat: mocks.connectFloat,
  getGmailAuthUrl: mocks.getGmailAuthUrl,
}));

vi.mock("@mergeapi/react-merge-link", () => ({
  useMergeLink: ({ onSuccess }: { onSuccess: (token: string) => void }) => ({
    open: () => {
      mocks.openMergeLink();
      onSuccess("public-token");
    },
    isReady: true,
  }),
}));

import IntegrationsPage from "./page";

describe("IntegrationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchIntegrations.mockResolvedValue([makeIntegration()]);
    mocks.createIntegration.mockResolvedValue(
      makeIntegration({ id: "integration-2", provider: "netsuite", integration_name: "NetSuite" })
    );
    mocks.createLinkToken.mockResolvedValue({ link_token: "link-token" });
    mocks.connectFloat.mockResolvedValue(
      makeIntegration({ id: "integration-3", provider: "float", integration_name: "Float" })
    );
    mocks.deleteIntegration.mockResolvedValue(undefined);
    vi.stubGlobal("confirm", vi.fn(() => true));
    window.history.replaceState({}, "", "/chat/integrations");
  });

  it("handles Gmail success query params and clears the URL", async () => {
    window.history.replaceState({}, "", "/chat/integrations?gmail=connected");

    render(<IntegrationsPage />);

    expect(await screen.findByText("Gmail connected successfully!")).toBeInTheDocument();
    await waitFor(() =>
      expect(window.location.search).toBe("")
    );
  });

  it("opens the accounting merge flow and appends the created integration", async () => {
    mocks.fetchIntegrations.mockResolvedValue([]);
    render(<IntegrationsPage />);

    fireEvent.click((await screen.findAllByText("Connect"))[0]);

    await waitFor(() => expect(mocks.createLinkToken).toHaveBeenCalled());
    await waitFor(() => expect(mocks.openMergeLink).toHaveBeenCalled());
    expect(mocks.createIntegration).toHaveBeenCalledWith(
      "public-token",
      "quickbooks",
      "QuickBooks Online"
    );
    expect(await screen.findByText("QuickBooks Online connected!")).toBeInTheDocument();
  });

  it("connects Float through the token dialog and supports disconnecting", async () => {
    mocks.fetchIntegrations.mockResolvedValue([makeIntegration()]);
    render(<IntegrationsPage />);

    const floatDesc = await screen.findByText(
      "Connect card and account transactions from Float Financial."
    );
    const floatCard = floatDesc.closest("div[class*='rounded-2xl']") as HTMLElement;
    const floatConnect = floatCard.querySelector("button") as HTMLButtonElement;
    fireEvent.click(floatConnect);

    expect(await screen.findByText("Connect Float")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("float_api_XXXXXXXXXX"), {
      target: { value: "float_api_secret" },
    });
    fireEvent.click(screen.getAllByText("Connect", { selector: "button" }).at(-1)!);

    await waitFor(() =>
      expect(mocks.connectFloat).toHaveBeenCalledWith("float_api_secret")
    );
    expect(await screen.findByText("Float connected successfully!")).toBeInTheDocument();

    fireEvent.click(screen.getAllByTitle("Disconnect")[0]);
    await waitFor(() => expect(mocks.deleteIntegration).toHaveBeenCalledWith("integration-3"));
  });
});
