"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Receipt,
  Loader2,
  AlertCircle,
  ExternalLink,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  X,
  FilterX,
  ChevronRight,
  ChevronDown,
  Layers,
} from "lucide-react";
import type { AccountingTransaction } from "@/types";
import { fetchTransactions } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ── Types ────────────────────────────────────────────────────

type SortField =
  | "transaction_date"
  | "contact_name"
  | "account_name"
  | "transaction_type"
  | "total_amount";
type SortDirection = "asc" | "desc";
type GroupField = "none" | "account_name" | "transaction_type" | "transaction_date";

interface TransactionGroup {
  key: string;
  label: string;
  transactions: AccountingTransaction[];
  totalAmount: number;
  currency: string;
}

// ── Helpers ──────────────────────────────────────────────────

function formatCurrency(amount: number | null, currency: string): string {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: 2,
  }).format(Math.abs(amount));
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function transactionTypeLabel(type: string | null): string {
  if (!type) return "Unknown";
  const labels: Record<string, string> = {
    expense: "Expense",
    income: "Income",
    journal_entry: "Journal Entry",
    payment: "Payment",
    bill: "Bill",
    invoice: "Invoice",
    credit_note: "Credit Note",
    transfer: "Transfer",
    deposit: "Deposit",
    refund: "Refund",
  };
  return (
    labels[type.toLowerCase()] ||
    type.charAt(0).toUpperCase() + type.slice(1)
  );
}

function typeBadgeVariant(
  type: string | null
): "default" | "secondary" | "destructive" | "outline" {
  const t = (type || "").toLowerCase();
  if (t === "income" || t === "invoice" || t === "deposit") return "default";
  if (t === "expense" || t === "bill" || t === "payment") return "destructive";
  return "secondary";
}

function amountColor(_type: string | null, amount: number | null): string {
  if (amount === null) return "text-muted-foreground";
  return "text-foreground";
}

function amountPrefix(type: string | null, amount: number | null): string {
  if (amount === null) return "";
  const t = (type || "").toLowerCase();
  if ((t === "expense" || t === "bill" || t === "payment") && amount > 0)
    return "−";
  if ((t === "income" || t === "invoice" || t === "deposit") && amount > 0)
    return "+";
  return "";
}

/** Build an external URL for the source accounting system. */
function getExternalUrl(txn: AccountingTransaction): string | null {
  const provider = (txn.provider || "").toLowerCase();
  if (provider === "quickbooks" && txn.remote_id) {
    return `https://app.qbo.intuit.com/app/expense?txnId=${txn.remote_id}`;
  }
  if (provider === "xero" && txn.remote_id) {
    return `https://go.xero.com/Bank/ViewTransaction.aspx?bankTransactionID=${txn.remote_id}`;
  }
  return null;
}

// ── Sort icon component ──────────────────────────────────────

function SortIcon({
  field,
  currentField,
  direction,
}: {
  field: SortField;
  currentField: SortField;
  direction: SortDirection;
}) {
  if (field !== currentField) {
    return <ArrowUpDown className="ml-1 size-3 text-muted-foreground/50" />;
  }
  return direction === "asc" ? (
    <ArrowUp className="ml-1 size-3" />
  ) : (
    <ArrowDown className="ml-1 size-3" />
  );
}

// ── Transaction row component ────────────────────────────────

function TransactionRow({ txn }: { txn: AccountingTransaction }) {
  const externalUrl = getExternalUrl(txn);

  return (
    <TableRow>
      {/* Date */}
      <TableCell className="text-muted-foreground text-xs">
        {formatDate(txn.transaction_date)}
      </TableCell>

      {/* Vendor */}
      <TableCell>
        <div className="flex flex-col gap-0.5">
          <span className="font-medium text-foreground truncate max-w-[220px]">
            {txn.contact_name || "—"}
          </span>
          {txn.memo && (
            <span className="text-xs text-muted-foreground truncate max-w-[220px]">
              {txn.memo}
            </span>
          )}
        </div>
      </TableCell>

      {/* Account */}
      <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">
        <span
          className="truncate max-w-[180px] inline-block"
          title={txn.account_name || ""}
        >
          {txn.account_name || "—"}
        </span>
      </TableCell>

      {/* Type */}
      <TableCell>
        <Badge
          variant={typeBadgeVariant(txn.transaction_type)}
          className="text-[11px]"
        >
          {transactionTypeLabel(txn.transaction_type)}
        </Badge>
      </TableCell>

      {/* Amount */}
      <TableCell className="text-right">
        <span
          className={`font-medium tabular-nums ${amountColor(
            txn.transaction_type,
            txn.total_amount
          )}`}
        >
          {amountPrefix(txn.transaction_type, txn.total_amount)}
          {formatCurrency(txn.total_amount, txn.currency)}
        </span>
      </TableCell>

      {/* Source dates */}
      <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
        <div className="flex flex-col gap-0.5">
          {txn.remote_created_at && (
            <span>{formatDateTime(txn.remote_created_at)}</span>
          )}
          {txn.remote_updated_at &&
            txn.remote_updated_at !== txn.remote_created_at && (
              <span className="text-muted-foreground/60">
                Upd. {formatDateTime(txn.remote_updated_at)}
              </span>
            )}
        </div>
      </TableCell>

      {/* External link */}
      <TableCell>
        {externalUrl ? (
          <a
            href={externalUrl}
            target="_blank"
            rel="noopener noreferrer"
            title={`View in ${txn.integration_name || "source"}`}
          >
            <Button
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground hover:text-cyan-500"
              asChild
            >
              <span>
                <ExternalLink className="size-3.5" />
              </span>
            </Button>
          </a>
        ) : null}
      </TableCell>
    </TableRow>
  );
}

// ── Page Component ───────────────────────────────────────────

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<AccountingTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [accountFilter, setAccountFilter] = useState<string>("all");

  // Sorting
  const [sortField, setSortField] = useState<SortField>("transaction_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Grouping
  const [groupBy, setGroupBy] = useState<GroupField>("none");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const loadTransactions = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchTransactions();
      setTransactions(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load transactions"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTransactions();
  }, [loadTransactions]);

  // ── Derived filter options ────────────────────────────────

  const transactionTypes = useMemo(() => {
    const types = new Set<string>();
    transactions.forEach((txn) => {
      if (txn.transaction_type) types.add(txn.transaction_type);
    });
    return Array.from(types).sort();
  }, [transactions]);

  const accountNames = useMemo(() => {
    const names = new Set<string>();
    transactions.forEach((txn) => {
      if (txn.account_name) names.add(txn.account_name);
    });
    return Array.from(names).sort();
  }, [transactions]);

  // ── Filtered + sorted data ────────────────────────────────

  const filteredAndSorted = useMemo(() => {
    let result = [...transactions];

    // Text search
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (txn) =>
          (txn.contact_name || "").toLowerCase().includes(q) ||
          (txn.account_name || "").toLowerCase().includes(q) ||
          (txn.memo || "").toLowerCase().includes(q) ||
          (txn.number || "").toLowerCase().includes(q) ||
          (txn.transaction_type || "").toLowerCase().includes(q) ||
          formatCurrency(txn.total_amount, txn.currency)
            .toLowerCase()
            .includes(q)
      );
    }

    // Type filter
    if (typeFilter !== "all") {
      result = result.filter((txn) => txn.transaction_type === typeFilter);
    }

    // Account filter
    if (accountFilter !== "all") {
      result = result.filter((txn) => txn.account_name === accountFilter);
    }

    // Sort
    result.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "transaction_date": {
          const da = a.transaction_date || "";
          const db = b.transaction_date || "";
          cmp = da.localeCompare(db);
          break;
        }
        case "contact_name": {
          const ca = (a.contact_name || "").toLowerCase();
          const cb = (b.contact_name || "").toLowerCase();
          cmp = ca.localeCompare(cb);
          break;
        }
        case "account_name": {
          const aa = (a.account_name || "").toLowerCase();
          const ab = (b.account_name || "").toLowerCase();
          cmp = aa.localeCompare(ab);
          break;
        }
        case "transaction_type": {
          const ta = (a.transaction_type || "").toLowerCase();
          const tb = (b.transaction_type || "").toLowerCase();
          cmp = ta.localeCompare(tb);
          break;
        }
        case "total_amount": {
          const va = a.total_amount ?? 0;
          const vb = b.total_amount ?? 0;
          cmp = va - vb;
          break;
        }
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });

    return result;
  }, [transactions, search, typeFilter, accountFilter, sortField, sortDirection]);

  // ── Grouped data ──────────────────────────────────────────

  const groupedData = useMemo((): TransactionGroup[] | null => {
    if (groupBy === "none") return null;

    const groups = new Map<string, AccountingTransaction[]>();

    for (const txn of filteredAndSorted) {
      let key: string;
      switch (groupBy) {
        case "account_name":
          key = txn.account_name || "Unknown Account";
          break;
        case "transaction_type":
          key = txn.transaction_type || "unknown";
          break;
        case "transaction_date":
          key = txn.transaction_date
            ? new Date(txn.transaction_date).toLocaleDateString("en-US", {
                month: "long",
                year: "numeric",
              })
            : "No Date";
          break;
        default:
          key = "Other";
      }
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(txn);
    }

    return Array.from(groups.entries()).map(([key, txns]) => ({
      key,
      label: groupBy === "transaction_type" ? transactionTypeLabel(key) : key,
      transactions: txns,
      totalAmount: txns.reduce((sum, t) => sum + (t.total_amount ?? 0), 0),
      currency: txns[0]?.currency || "USD",
    }));
  }, [filteredAndSorted, groupBy]);

  // ── Handlers ──────────────────────────────────────────────

  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleGroupByChange = (value: string) => {
    setGroupBy(value as GroupField);
    setCollapsedGroups(new Set());
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection(field === "total_amount" ? "desc" : "asc");
    }
  };

  const hasActiveFilters =
    search !== "" || typeFilter !== "all" || accountFilter !== "all";

  const clearFilters = () => {
    setSearch("");
    setTypeFilter("all");
    setAccountFilter("all");
  };

  // ── Render ────────────────────────────────────────────────

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-2">
          <Receipt size={20} className="text-cyan-400" />
          <h1 className="text-lg font-semibold text-foreground">
            Transactions
          </h1>
          {!loading && (
            <span className="ml-1 text-sm text-muted-foreground">
              ({filteredAndSorted.length}
              {hasActiveFilters &&
              filteredAndSorted.length !== transactions.length
                ? ` of ${transactions.length}`
                : ""}
              )
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 py-4 space-y-4">
          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3">
              <AlertCircle size={16} className="shrink-0 text-destructive" />
              <p className="text-sm text-destructive">{error}</p>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-xs text-destructive/60 hover:text-destructive"
              >
                Dismiss
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 size={20} className="animate-spin" />
                <span className="text-sm">Loading transactions...</span>
              </div>
            </div>
          ) : transactions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
                <Receipt size={28} className="text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-muted-foreground">
                No transactions yet
              </p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                Connect an accounting integration and sync your data to see
                transactions here.
              </p>
            </div>
          ) : (
            <>
              {/* Filter bar */}
              <div className="flex flex-wrap items-center gap-3">
                {/* Search */}
                <div className="relative flex-1 min-w-[200px] max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    placeholder="Search transactions..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-9 pr-8"
                  />
                  {search && (
                    <button
                      onClick={() => setSearch("")}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                {/* Type filter */}
                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="All Types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {transactionTypes.map((t) => (
                      <SelectItem key={t} value={t}>
                        {transactionTypeLabel(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Account filter */}
                <Select value={accountFilter} onValueChange={setAccountFilter}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="All Accounts" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Accounts</SelectItem>
                    {accountNames.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Group by */}
                <Select value={groupBy} onValueChange={handleGroupByChange}>
                  <SelectTrigger className="w-[180px]">
                    <Layers className="size-3.5 shrink-0 text-muted-foreground" />
                    <SelectValue placeholder="Group by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No Grouping</SelectItem>
                    <SelectItem value="account_name">Group by Account</SelectItem>
                    <SelectItem value="transaction_type">Group by Type</SelectItem>
                    <SelectItem value="transaction_date">Group by Month</SelectItem>
                  </SelectContent>
                </Select>

                {/* Clear filters */}
                {hasActiveFilters && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearFilters}
                    className="text-muted-foreground"
                  >
                    <FilterX className="size-4" />
                    Clear
                  </Button>
                )}
              </div>

              {/* Table */}
              {filteredAndSorted.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    No transactions match your filters.
                  </p>
                  <Button
                    variant="link"
                    size="sm"
                    onClick={clearFilters}
                    className="mt-1"
                  >
                    Clear all filters
                  </Button>
                </div>
              ) : (
                <div className="rounded-xl border border-border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/40 hover:bg-muted/40">
                        <TableHead className="w-[120px]">
                          <button
                            className="inline-flex items-center hover:text-foreground transition-colors"
                            onClick={() => handleSort("transaction_date")}
                          >
                            Date
                            <SortIcon
                              field="transaction_date"
                              currentField={sortField}
                              direction={sortDirection}
                            />
                          </button>
                        </TableHead>
                        <TableHead>
                          <button
                            className="inline-flex items-center hover:text-foreground transition-colors"
                            onClick={() => handleSort("contact_name")}
                          >
                            Vendor
                            <SortIcon
                              field="contact_name"
                              currentField={sortField}
                              direction={sortDirection}
                            />
                          </button>
                        </TableHead>
                        <TableHead className="hidden lg:table-cell">
                          <button
                            className="inline-flex items-center hover:text-foreground transition-colors"
                            onClick={() => handleSort("account_name")}
                          >
                            Account
                            <SortIcon
                              field="account_name"
                              currentField={sortField}
                              direction={sortDirection}
                            />
                          </button>
                        </TableHead>
                        <TableHead className="w-[130px]">
                          <button
                            className="inline-flex items-center hover:text-foreground transition-colors"
                            onClick={() => handleSort("transaction_type")}
                          >
                            Type
                            <SortIcon
                              field="transaction_type"
                              currentField={sortField}
                              direction={sortDirection}
                            />
                          </button>
                        </TableHead>
                        <TableHead className="w-[140px] text-right">
                          <button
                            className="inline-flex items-center ml-auto hover:text-foreground transition-colors"
                            onClick={() => handleSort("total_amount")}
                          >
                            Amount
                            <SortIcon
                              field="total_amount"
                              currentField={sortField}
                              direction={sortDirection}
                            />
                          </button>
                        </TableHead>
                        <TableHead className="hidden md:table-cell w-[160px]">
                          Source
                        </TableHead>
                        <TableHead className="w-[50px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {groupedData
                        ? groupedData.map((group) => {
                            const isCollapsed = collapsedGroups.has(group.key);
                            return (
                              <React.Fragment key={group.key}>
                                {/* Group header row */}
                                <TableRow
                                  className="bg-muted/60 hover:bg-muted/80 cursor-pointer"
                                  onClick={() => toggleGroup(group.key)}
                                >
                                  <TableCell colSpan={7} className="py-2">
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        {isCollapsed ? (
                                          <ChevronRight className="size-4 text-muted-foreground" />
                                        ) : (
                                          <ChevronDown className="size-4 text-muted-foreground" />
                                        )}
                                        <span className="font-medium text-sm text-foreground">
                                          {group.label}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                          ({group.transactions.length})
                                        </span>
                                      </div>
                                      <span className="font-medium tabular-nums text-sm text-foreground">
                                        {formatCurrency(
                                          group.totalAmount,
                                          group.currency
                                        )}
                                      </span>
                                    </div>
                                  </TableCell>
                                </TableRow>
                                {/* Group rows */}
                                {!isCollapsed &&
                                  group.transactions.map((txn) => (
                                    <TransactionRow key={txn.id} txn={txn} />
                                  ))}
                              </React.Fragment>
                            );
                          })
                        : filteredAndSorted.map((txn) => (
                            <TransactionRow key={txn.id} txn={txn} />
                          ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
