import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  CheckCircle,
  Clock,
  Link2,
  Plus,
  Shield,
  ShieldAlert,
  UserCheck,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";
import {
  departmentApi,
  type DepartmentUser,
  type UserProfile,
} from "@/lib/iris/department-api";
import { useAuth } from "@/lib/auth-context";
import { PageShell, PageHeader } from "@/components/iris/page";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/department/officers")({
  head: () => ({ meta: [{ title: "Officers & User Management — IRIS Gov" }] }),
  component: OfficersManagementPage,
});

function OfficersManagementPage() {
  const queryClient = useQueryClient();
  const { irisUser, isDemoMode } = useAuth();
  const isAdmin = isDemoMode || irisUser?.role === "DEPARTMENT_ADMIN";

  const [activeTab, setActiveTab] = useState<"officers" | "pending">(
    "officers",
  );
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [linkingProfile, setLinkingProfile] = useState<UserProfile | null>(
    null,
  );

  // Form states for manual creation
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("DEPARTMENT_OFFICER");
  const [newDeptId, setNewDeptId] = useState("dept-mpcb");

  // Form states for linking profile
  const [linkRole, setLinkRole] = useState("DEPARTMENT_OFFICER");
  const [linkDeptId, setLinkDeptId] = useState("dept-mpcb");

  // Queries
  const { data: officers, isLoading: loadingOfficers } = useQuery({
    queryKey: ["department", "users"],
    queryFn: () => departmentApi.listDepartmentUsers(),
  });

  const { data: userProfiles, isLoading: loadingProfiles } = useQuery({
    queryKey: ["department", "user-profiles"],
    queryFn: () => departmentApi.listUserProfiles(false),
    enabled: isAdmin,
  });

  // Mutations
  const updateUserMutation = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { is_active?: boolean; role?: string };
    }) => departmentApi.updateDepartmentUser(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["department", "users"] });
      void queryClient.invalidateQueries({
        queryKey: ["department", "user-profiles"],
      });
    },
  });

  const createUserMutation = useMutation({
    mutationFn: (data: {
      name: string;
      email?: string;
      role: string;
      department_id: string;
    }) => departmentApi.createDepartmentUser(data),
    onSuccess: () => {
      setShowCreateModal(false);
      setNewName("");
      setNewEmail("");
      void queryClient.invalidateQueries({ queryKey: ["department", "users"] });
    },
  });

  const linkProfileMutation = useMutation({
    mutationFn: (data: {
      user_profile_id: string;
      department_id: string;
      role: string;
      name?: string;
    }) => departmentApi.linkUserProfile(data),
    onSuccess: () => {
      setLinkingProfile(null);
      void queryClient.invalidateQueries({ queryKey: ["department", "users"] });
      void queryClient.invalidateQueries({
        queryKey: ["department", "user-profiles"],
      });
    },
  });

  // Filter profiles: unlinked or pending government access
  const pendingProfiles = (userProfiles ?? []).filter(
    (p) => p.iris_role === "INDUSTRY_USER" || p.pending_government_link,
  );

  return (
    <PageShell wide>
      <PageHeader
        trail={[
          { label: "Department", to: "/department" },
          { label: "Officers & Access" },
        ]}
        title="Officers & User Access"
        description="Government officer roster, authority delegation, and Supabase / Google OAuth user provisioning."
        actions={
          isAdmin && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-[12.5px] font-medium text-primary-foreground shadow-sm hover:opacity-90"
            >
              <UserPlus className="h-4 w-4" />
              Add Officer
            </button>
          )
        }
      />

      {/* Admin Notice */}
      {!isAdmin && (
        <div className="mt-4 rounded-lg border border-border bg-muted/20 p-3.5 text-[12.5px] text-muted-foreground">
          You are viewing the officer roster as a{" "}
          <strong>{irisUser?.role}</strong>. Only{" "}
          <strong>DEPARTMENT_ADMIN</strong> users can provision new accounts,
          modify roles, or link Supabase/Google identities.
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex border-b border-border">
        <button
          onClick={() => setActiveTab("officers")}
          className={cn(
            "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors",
            activeTab === "officers"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Department Officers ({officers?.length ?? 0})
        </button>
        {isAdmin && (
          <button
            onClick={() => setActiveTab("pending")}
            className={cn(
              "border-b-2 px-4 py-2 text-[13px] font-medium transition-colors flex items-center gap-2",
              activeTab === "pending"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <span>Unlinked / Pending Identities</span>
            {pendingProfiles.length > 0 && (
              <span className="rounded-full bg-warning/20 px-2 py-0.5 text-[10.5px] font-semibold text-warning">
                {pendingProfiles.length}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Tab 1: Department Officers */}
      {activeTab === "officers" && (
        <div className="mt-4">
          {loadingOfficers && (
            <p className="mb-2 text-[12px] text-muted-foreground">
              Loading department officers…
            </p>
          )}
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Officer Name</th>
                  <th className="px-4 py-3">Department</th>
                  <th className="px-4 py-3">Government Role</th>
                  <th className="px-4 py-3">Identity Status</th>
                  <th className="px-4 py-3">Active Status</th>
                  {isAdmin && <th className="px-4 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {officers?.map((off) => (
                  <tr
                    key={off.id}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-foreground">
                      <div>{off.name}</div>
                      {off.email && (
                        <div className="text-[11.5px] text-muted-foreground font-normal">
                          {off.email}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {off.department_name ?? off.department_id}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded border border-border bg-secondary/50 px-2 py-0.5 text-[11px] font-medium">
                        {off.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[12px] text-muted-foreground">
                      {off.supabase_auth_uid ? (
                        <span className="inline-flex items-center gap-1 text-success">
                          <CheckCircle className="h-3.5 w-3.5" /> Supabase
                          Linked
                        </span>
                      ) : (
                        <span className="text-muted-foreground/70 italic">
                          Manual Entry
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {off.is_active ? (
                        <span className="inline-flex items-center gap-1 text-[11.5px] text-success">
                          <span className="h-1.5 w-1.5 rounded-full bg-success" />{" "}
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11.5px] text-destructive">
                          <span className="h-1.5 w-1.5 rounded-full bg-destructive" />{" "}
                          Deactivated
                        </span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() =>
                            updateUserMutation.mutate({
                              id: off.id,
                              data: { is_active: !off.is_active },
                            })
                          }
                          className={cn(
                            "rounded border px-2.5 py-1 text-[11.5px] font-medium transition-colors",
                            off.is_active
                              ? "border-border text-muted-foreground hover:border-destructive hover:text-destructive"
                              : "border-success/40 text-success hover:bg-success-surface",
                          )}
                        >
                          {off.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
                {!loadingOfficers && (!officers || officers.length === 0) && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No officers registered.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Pending / Unlinked Identities (ADMIN ONLY) */}
      {activeTab === "pending" && isAdmin && (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="text-[14px] font-semibold">
              External Identities Awaiting Government Assignment
            </h3>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground leading-relaxed">
              Users who signed in via Google OAuth or Email start with an
              Industry profile. Google authentication alone does{" "}
              <strong>NOT</strong> grant Government portal access.
              Administrators must explicitly assign a department and role below.
            </p>
          </div>

          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Auth Provider</th>
                  <th className="px-4 py-3">Current IRIS Role</th>
                  <th className="px-4 py-3">Registered At</th>
                  <th className="px-4 py-3 text-right">Grant Access</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pendingProfiles.map((p) => (
                  <tr key={p.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">
                        {p.full_name || "Anonymous User"}
                      </div>
                      <div className="text-[11.5px] text-muted-foreground">
                        {p.email || p.supabase_auth_uid}
                      </div>
                    </td>
                    <td className="px-4 py-3 uppercase text-[11.5px] text-muted-foreground font-mono">
                      {p.provider || "email"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded border border-border bg-secondary/40 px-2 py-0.5 text-[11px]">
                        {p.iris_role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[12px] text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setLinkingProfile(p)}
                        className="inline-flex items-center gap-1 rounded bg-primary px-2.5 py-1 text-[11.5px] font-medium text-primary-foreground hover:opacity-90"
                      >
                        <Link2 className="h-3 w-3" />
                        Assign Government Role
                      </button>
                    </td>
                  </tr>
                ))}
                {pendingProfiles.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No unlinked identities awaiting assignment.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Manual Create Officer */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
            <h3 className="text-[16px] font-semibold text-foreground">
              Add Department Officer
            </h3>
            <p className="mt-1 text-[12.5px] text-muted-foreground">
              Directly register an operational officer into the department
              system.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createUserMutation.mutate({
                  name: newName,
                  ...(newEmail ? { email: newEmail } : {}),
                  role: newRole,
                  department_id: newDeptId,
                });
              }}
              className="mt-4 space-y-3 text-[13px]"
            >
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Full Name
                </label>
                <input
                  required
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Officer name"
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Email (optional)
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="officer@example.com"
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Department
                </label>
                <select
                  value={newDeptId}
                  onChange={(e) => setNewDeptId(e.target.value)}
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                >
                  <option value="dept-mpcb">
                    Maharashtra Pollution Control Board (MPCB)
                  </option>
                  <option value="dept-fssai">
                    Food Safety & Standards Authority (FSSAI)
                  </option>
                </select>
              </div>
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Role
                </label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                >
                  <option value="DEPARTMENT_OFFICER">DEPARTMENT_OFFICER</option>
                  <option value="DEPARTMENT_MANAGER">DEPARTMENT_MANAGER</option>
                  <option value="DEPARTMENT_ADMIN">DEPARTMENT_ADMIN</option>
                </select>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded border border-border px-3 py-1.5 text-[12.5px] hover:bg-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createUserMutation.isPending}
                  className="rounded bg-primary px-3.5 py-1.5 text-[12.5px] font-medium text-primary-foreground hover:opacity-90"
                >
                  {createUserMutation.isPending ? "Creating…" : "Add Officer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Link User Profile to Department */}
      {linkingProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
            <h3 className="text-[16px] font-semibold text-foreground">
              Grant Government Access
            </h3>
            <p className="mt-1 text-[12.5px] text-muted-foreground">
              Link{" "}
              <strong>
                {linkingProfile.full_name || linkingProfile.email}
              </strong>{" "}
              to an official authority department and role.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                linkProfileMutation.mutate({
                  user_profile_id: linkingProfile.id,
                  department_id: linkDeptId,
                  role: linkRole,
                  ...(linkingProfile.full_name
                    ? { name: linkingProfile.full_name }
                    : {}),
                });
              }}
              className="mt-4 space-y-3 text-[13px]"
            >
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Target Department
                </label>
                <select
                  value={linkDeptId}
                  onChange={(e) => setLinkDeptId(e.target.value)}
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                >
                  <option value="dept-mpcb">
                    Maharashtra Pollution Control Board (MPCB)
                  </option>
                  <option value="dept-fssai">
                    Food Safety & Standards Authority (FSSAI)
                  </option>
                </select>
              </div>
              <div>
                <label className="block text-[12px] font-medium mb-1">
                  Assign Government Role
                </label>
                <select
                  value={linkRole}
                  onChange={(e) => setLinkRole(e.target.value)}
                  className="w-full rounded border border-border bg-background px-3 py-1.5"
                >
                  <option value="DEPARTMENT_OFFICER">DEPARTMENT_OFFICER</option>
                  <option value="DEPARTMENT_MANAGER">DEPARTMENT_MANAGER</option>
                  <option value="DEPARTMENT_ADMIN">DEPARTMENT_ADMIN</option>
                </select>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setLinkingProfile(null)}
                  className="rounded border border-border px-3 py-1.5 text-[12.5px] hover:bg-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={linkProfileMutation.isPending}
                  className="rounded bg-primary px-3.5 py-1.5 text-[12.5px] font-medium text-primary-foreground hover:opacity-90"
                >
                  {linkProfileMutation.isPending
                    ? "Assigning…"
                    : "Confirm Assignment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PageShell>
  );
}
