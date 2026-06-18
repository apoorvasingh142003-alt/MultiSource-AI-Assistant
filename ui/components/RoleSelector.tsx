"use client";
import React from "react";
import type { RoleInfo } from "@/lib/types";
import { Card, Icons, Pill, SectionTitle } from "./ui";

/* Built-in roles available for role-based adaptation */
const AVAILABLE_ROLES: RoleInfo[] = [
  {
    name: "default",
    label: "Business Analyst",
    description: "Neutral, evidence-based responses with business focus",
    system_instruction: "Standard business analysis perspective",
  },
  {
    name: "doctor",
    label: "Doctor",
    description: "Medical expertise and clinical perspective",
    system_instruction: "Applies medical knowledge and clinical reasoning",
  },
  {
    name: "nurse",
    label: "Nurse",
    description: "Patient care, monitoring, and practical health guidance",
    system_instruction: "Patient care perspective with practical guidance",
  },
  {
    name: "business_analyst",
    label: "Business Analyst",
    description: "Requirements, impact, KPIs, workflows, and recommendations",
    system_instruction: "Strategic business analysis and recommendations",
  },
  {
    name: "software_engineer",
    label: "Software Engineer",
    description: "Architecture, scalability, maintainability, and implementation",
    system_instruction: "Technical architecture and implementation focus",
  },
  {
    name: "data_analyst",
    label: "Data Analyst",
    description: "Trends, metrics, patterns, and evidence-based insights",
    system_instruction: "Data-driven analysis with statistical insights",
  },
  {
    name: "project_manager",
    label: "Project Manager",
    description: "Scope, timeline, resources, risks, and deliverables",
    system_instruction: "Project management perspective with risk focus",
  },
  {
    name: "teacher",
    label: "Teacher",
    description: "Clear explanations with examples and step-by-step guidance",
    system_instruction: "Educational perspective with clear explanations",
  },
  {
    name: "financial_advisor",
    label: "Financial Advisor",
    description: "Financial implications, risks, opportunities, and decisions",
    system_instruction: "Financial analysis and decision-making focus",
  },
  {
    name: "lawyer",
    label: "Lawyer",
    description: "Legal implications, risk assessment, and compliance",
    system_instruction: "Legal perspective with compliance and risk focus",
  },
  {
    name: "consultant",
    label: "Consultant",
    description: "Strategic recommendations and best practices",
    system_instruction: "Strategic consulting with best practices",
  },
  {
    name: "marketing_strategist",
    label: "Marketing Strategist",
    description: "Market positioning, strategy, and customer insights",
    system_instruction: "Marketing strategy with market positioning",
  },
  {
    name: "hr_specialist",
    label: "HR Specialist",
    description: "People management, culture, and organizational development",
    system_instruction: "HR perspective with people and culture focus",
  },
];

export default function RoleSelector({
  selectedRole,
  onRoleChange,
}: {
  selectedRole: string | null;
  onRoleChange: (role: string | null) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const currentRole = selectedRole
    ? AVAILABLE_ROLES.find((r) => r.name === selectedRole)
    : AVAILABLE_ROLES[0];

  return (
    <Card className="p-4">
      <SectionTitle hint="AI will adapt its response style to this role">
        Response Style (Role)
      </SectionTitle>
      
      <div className="mb-3 space-y-2">
        <div className="text-[12.5px] font-medium text-slate-700">Current: {currentRole?.label}</div>
        <p className="text-[11.5px] leading-relaxed text-slate-500">
          {currentRole?.description}
        </p>
      </div>

      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-left text-[13px] font-medium text-slate-700 transition hover:border-indigo-300 hover:shadow-sm"
      >
        <div className="flex items-center justify-between gap-2">
          <span>{currentRole?.label}</span>
          <Icons.chevron className={`h-4 w-4 transition-transform ${open ? "rotate-90" : ""}`} />
        </div>
      </button>

      {open && (
        <div className="mt-3 max-h-60 space-y-1.5 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-2">
          {AVAILABLE_ROLES.map((role) => (
            <button
              key={role.name}
              onClick={() => {
                onRoleChange(role.name === "default" ? null : role.name);
                setOpen(false);
              }}
              className="w-full rounded-lg px-3 py-2 text-left transition hover:bg-white"
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-[12.5px] font-medium text-slate-700">
                    {role.label}
                  </div>
                  <div className="text-[11px] text-slate-500">{role.description}</div>
                </div>
                {selectedRole === role.name || (role.name === "default" && !selectedRole) ? (
                  <Icons.check className="h-4 w-4 shrink-0 text-indigo-600" />
                ) : (
                  <div className="h-4 w-4 rounded border border-slate-300" />
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
