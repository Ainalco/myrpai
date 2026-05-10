import React, { useState, useRef } from 'react';
import { 
  ArrowLeft, Settings, Upload, Download, Save, Plus, 
  Mail, ChevronRight, ChevronDown, Play, Copy, Check, Trash2,
  AlertCircle, Clock, Sparkles, Edit3, Code, CheckCircle, 
  AlignLeft, Zap, Brain, Calendar, Shield, SkipForward,
  Send, Timer, Target, FileText
} from 'lucide-react';

// Scurry Brand Colors
const colors = {
  hyperOrange: '#FF5722',
  espresso: '#3E2723',
  latte: '#795548',
  energyBurst: '#FFC107',
  goGreen: '#4CAF50',
  foam: '#FFF8E1',
  // Derived
  orangeLight: '#FFF3E0',
  orangeHover: '#E64A19',
  greenLight: '#E8F5E9',
  redLight: '#FFEBEE',
  red: '#F44336',
};

// Available variables from previous components
const availableVariables = [
  { id: 'component:Input Source', name: 'component:Input Source', description: 'All outputs from Input Source', icon: FileText },
  { id: 'transcript', name: 'transcript', description: 'Transcript (Input Source)', icon: FileText },
  { id: 'participants', name: 'participants', description: 'Participants (Input Source)', icon: FileText },
  { id: 'meeting_title', name: 'meeting_title', description: 'Meeting Title (Input Source)', icon: Calendar },
  { id: 'meeting_date', name: 'meeting_date', description: 'Meeting Date (Input Source)', icon: Calendar },
  { id: 'company_name', name: 'company_name', description: 'Company Name (Text Generation)', icon: FileText },
  { id: 'first_name', name: 'first_name', description: 'First Name (Text Generation)', icon: FileText },
  { id: 'key_points', name: 'key_points', description: 'Key Points (Text Generation)', icon: FileText },
  { id: 'action_items', name: 'action_items', description: 'Action Items (Text Generation)', icon: FileText },
  { id: 'next_steps', name: 'next_steps', description: 'Next Steps (Text Generation)', icon: FileText },
  { id: 'pain_points', name: 'pain_points', description: 'Pain Points (Text Generation)', icon: AlertCircle },
  { id: 'budget_discussed', name: 'budget_discussed', description: 'Budget Discussed (Text Generation)', icon: FileText },
  { id: 'timeline', name: 'timeline', description: 'Timeline (Text Generation)', icon: Clock },
  { id: 'keyInfoPrompts', name: 'keyInfoPrompts', description: 'Key Info Prompts (Text Generation)', icon: Sparkles },
];

// Variable Pill Component (matches Text Generation)
const VariablePill = ({ children }) => (
  <span style={{
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '2px 10px',
    backgroundColor: colors.hyperOrange,
    color: 'white',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '600',
    fontFamily: "'Space Mono', monospace",
    margin: '0 2px'
  }}>
    <Sparkles size={12} />
    {children}
  </span>
);

// Collapsible Section Component
const CollapsibleSection = ({ icon: Icon, title, badge, isOpen, onToggle, children }) => (
  <div style={{
    backgroundColor: 'white',
    borderRadius: '12px',
    border: `1px solid ${colors.foam}`,
    marginBottom: '20px',
    overflow: 'hidden'
  }}>
    <button
      onClick={onToggle}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 20px',
        backgroundColor: colors.foam + '40',
        border: 'none',
        borderBottom: isOpen ? `1px solid ${colors.foam}` : 'none',
        cursor: 'pointer',
        textAlign: 'left'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Icon size={18} color={colors.hyperOrange} />
        <h3 style={{ 
          fontSize: '15px', 
          fontWeight: '600', 
          color: colors.espresso,
          margin: 0
        }}>
          {title}
        </h3>
        {badge && (
          <span style={{
            padding: '3px 10px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: '600',
            backgroundColor: colors.energyBurst,
            color: colors.espresso
          }}>
            {badge}
          </span>
        )}
      </div>
      {isOpen ? <ChevronDown size={20} color={colors.latte} /> : <ChevronRight size={20} color={colors.latte} />}
    </button>

    {isOpen && (
      <div style={{ padding: '20px' }}>
        {children}
      </div>
    )}
  </div>
);

// Timing Mode Card Component
const TimingModeCard = ({ isSelected, icon: Icon, title, description, recommended, onClick }) => (
  <button
    onClick={onClick}
    style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '8px',
      padding: '16px 12px',
      backgroundColor: isSelected ? colors.orangeLight : 'white',
      border: `2px solid ${isSelected ? colors.hyperOrange : colors.foam}`,
      borderRadius: '12px',
      cursor: 'pointer',
      position: 'relative',
      transition: 'all 0.2s ease'
    }}
  >
    {recommended && (
      <span style={{
        position: 'absolute',
        top: '-10px',
        right: '10px',
        padding: '2px 8px',
        backgroundColor: colors.energyBurst,
        color: colors.espresso,
        fontSize: '10px',
        fontWeight: '700',
        borderRadius: '10px'
      }}>
        ⭐ BEST
      </span>
    )}
    <div style={{
      width: '48px',
      height: '48px',
      borderRadius: '12px',
      backgroundColor: isSelected ? colors.hyperOrange : colors.foam,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      <Icon size={24} color={isSelected ? 'white' : colors.hyperOrange} />
    </div>
    <span style={{ 
      fontSize: '14px', 
      fontWeight: '600', 
      color: colors.espresso 
    }}>
      {title}
    </span>
    <span style={{ 
      fontSize: '12px', 
      color: colors.latte,
      textAlign: 'center'
    }}>
      {description}
    </span>
  </button>
);

// Checkbox Component
const Checkbox = ({ checked, onChange, label, description }) => (
  <label style={{
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    padding: '12px',
    backgroundColor: checked ? colors.greenLight : 'transparent',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'background 0.15s'
  }}>
    <div style={{
      width: '20px',
      height: '20px',
      borderRadius: '4px',
      border: `2px solid ${checked ? colors.goGreen : colors.latte}40`,
      backgroundColor: checked ? colors.goGreen : 'white',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
      marginTop: '2px'
    }}>
      {checked && <Check size={14} color="white" />}
    </div>
    <div>
      <div style={{ fontSize: '14px', fontWeight: '500', color: colors.espresso }}>
        {label}
      </div>
      {description && (
        <div style={{ fontSize: '12px', color: colors.latte, marginTop: '2px' }}>
          {description}
        </div>
      )}
    </div>
  </label>
);

// Toggle Switch Component
const ToggleSwitch = ({ checked, onChange }) => (
  <button
    onClick={() => onChange(!checked)}
    style={{
      width: '44px',
      height: '24px',
      borderRadius: '12px',
      backgroundColor: checked ? colors.goGreen : colors.latte + '40',
      border: 'none',
      cursor: 'pointer',
      position: 'relative',
      transition: 'background 0.2s'
    }}
  >
    <div style={{
      position: 'absolute',
      top: '2px',
      left: checked ? '22px' : '2px',
      width: '20px',
      height: '20px',
      borderRadius: '50%',
      backgroundColor: 'white',
      boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
      transition: 'left 0.2s'
    }} />
  </button>
);

// Variable Dropdown Component
const VariableDropdown = ({ variables, onSelect, onClose, position }) => (
  <div 
    style={{
      position: 'fixed',
      top: position.top,
      left: position.left,
      zIndex: 1000,
      width: '320px',
      maxHeight: '300px',
      overflowY: 'auto',
      backgroundColor: 'white',
      borderRadius: '12px',
      boxShadow: '0 8px 32px rgba(62, 39, 35, 0.2)',
      border: `2px solid ${colors.hyperOrange}`,
    }}
  >
    {/* Header */}
    <div style={{
      padding: '12px 16px',
      backgroundColor: colors.foam,
      borderBottom: `1px solid ${colors.foam}`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Sparkles size={16} color={colors.hyperOrange} />
        <span style={{ fontSize: '13px', fontWeight: '600', color: colors.espresso }}>
          Insert Variable
        </span>
      </div>
      <button
        onClick={onClose}
        style={{
          background: 'none',
          border: 'none',
          color: colors.latte,
          cursor: 'pointer',
          fontSize: '18px',
          lineHeight: 1
        }}
      >
        ×
      </button>
    </div>
    
    {/* Variable List */}
    <div style={{ padding: '8px' }}>
      {variables.map((variable) => {
        const IconComponent = variable.icon;
        return (
          <button
            key={variable.id}
            onClick={() => onSelect(variable.id)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '10px 12px',
              backgroundColor: 'transparent',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'background 0.15s'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = colors.orangeLight}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: colors.foam,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              <IconComponent size={16} color={colors.hyperOrange} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: '13px',
                fontWeight: '600',
                color: colors.espresso,
                fontFamily: "'Space Mono', monospace"
              }}>
                {`{{${variable.name}}}`}
              </div>
              <div style={{
                fontSize: '11px',
                color: colors.latte,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}>
                {variable.description}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  </div>
);

export default function EmailSequenceConfig() {
  // Email state
  const [emails, setEmails] = useState([
    { 
      id: 1, 
      emailPrompt: '### Objective\nCreate a personalized follow-up email based on the meeting transcript.\n\n### Key Information\nUse the following extracted information:\n{{key_points}}\n{{action_items}}\n{{next_steps}}\n\n### Tone\nProfessional but friendly, matching the Scurry brand voice.', 
      subjectPrompt: 'Generate a compelling subject line based on {{meeting_title}} and {{key_points}}' 
    },
    { id: 2, emailPrompt: '', subjectPrompt: '' },
    { id: 3, emailPrompt: '', subjectPrompt: '' },
  ]);
  const [currentEmailIndex, setCurrentEmailIndex] = useState(0);

  // Section expansion state
  const [promptExpanded, setPromptExpanded] = useState(true);
  const [timingExpanded, setTimingExpanded] = useState(true);
  const [deliveryExpanded, setDeliveryExpanded] = useState(false);
  const [skipExpanded, setSkipExpanded] = useState(false);

  // Prompt editing state
  const [isEditingEmailPrompt, setIsEditingEmailPrompt] = useState(false);
  const [isEditingSubjectPrompt, setIsEditingSubjectPrompt] = useState(false);
  const [showVariableDropdown, setShowVariableDropdown] = useState(null); // 'email' | 'subject' | null
  const [variableDropdownPosition, setVariableDropdownPosition] = useState({ top: 0, left: 0 });
  const [copiedEmailPrompt, setCopiedEmailPrompt] = useState(false);
  const [copiedSubjectPrompt, setCopiedSubjectPrompt] = useState(false);
  
  // Refs for textareas
  const emailPromptRef = useRef(null);
  const subjectPromptRef = useRef(null);

  // Test state
  const [testDataSource, setTestDataSource] = useState('mock');
  const [showTestResults, setShowTestResults] = useState(false);
  const [copiedResults, setCopiedResults] = useState(false);
  const [resultsViewMode, setResultsViewMode] = useState('formatted');

  // Per-email timing configs
  const [timingConfigs, setTimingConfigs] = useState([
    { 
      mode: 'immediate',
      timingType: 'relative', // 'relative' | 'specific_day'
      delayValue: 0, 
      delayUnit: 'hours',
      specificDay: 'next_monday',
      specificTime: '10:00',
      // Fixed Delay AI optimization
      aiOptimization: true,
      aiOptimizationType: 'basic', // 'basic' | 'custom'
      aiCustomTimingPrompt: '',
      aiMaxAdjustment: '1_week',
      // AI Decides custom prompt (optional)
      aiDecidesPrompt: '',
    },
    { 
      mode: 'fixed_delay',
      timingType: 'relative',
      delayValue: 3, 
      delayUnit: 'days',
      specificDay: 'next_monday',
      specificTime: '10:00',
      aiOptimization: true,
      aiOptimizationType: 'basic',
      aiCustomTimingPrompt: '',
      aiMaxAdjustment: '1_week',
      aiDecidesPrompt: '',
    },
    { 
      mode: 'ai_decides',
      timingType: 'specific_day',
      delayValue: 5, 
      delayUnit: 'days',
      specificDay: 'next_friday',
      specificTime: '14:00',
      aiOptimization: false,
      aiOptimizationType: 'basic',
      aiCustomTimingPrompt: '',
      aiMaxAdjustment: '3_days',
      aiDecidesPrompt: 'If the prospect mentioned they are traveling or OOO, wait until they return. If urgency was expressed, prioritize sending within 24-48 hours.',
    },
  ]);

  // Delivery settings
  const [deliverySettings, setDeliverySettings] = useState({
    businessHoursOnly: true,
    businessStart: '09:00',
    businessEnd: '17:00',
    respectTimezone: true,
    avoidWeekends: true,
  });

  // Skip conditions
  const [skipConditions, setSkipConditions] = useState({
    ifResponded: true,
    ifMeetingScheduled: true,
    ifDealStageChanged: false,
    dealStage: '',
    ifBounced: true,
  });

  const currentEmail = emails[currentEmailIndex];
  const currentTiming = timingConfigs[currentEmailIndex];

  const handleCopy = (type) => {
    if (type === 'email') {
      setCopiedEmailPrompt(true);
      setTimeout(() => setCopiedEmailPrompt(false), 2000);
    } else {
      setCopiedSubjectPrompt(true);
      setTimeout(() => setCopiedSubjectPrompt(false), 2000);
    }
  };

  const handleCopyResults = () => {
    setCopiedResults(true);
    setTimeout(() => setCopiedResults(false), 2000);
  };

  const updateTimingConfig = (key, value) => {
    setTimingConfigs(prev => {
      const updated = [...prev];
      updated[currentEmailIndex] = { ...updated[currentEmailIndex], [key]: value };
      return updated;
    });
  };

  const updateEmailPrompt = (field, value) => {
    setEmails(prev => {
      const updated = [...prev];
      updated[currentEmailIndex] = { ...updated[currentEmailIndex], [field]: value };
      return updated;
    });
  };

  // Handle typing in prompt editor - detect {{ for variable dropdown
  const handlePromptChange = (field, value, textareaRef) => {
    updateEmailPrompt(field, value);
    
    // Check if user just typed {{
    const cursorPos = textareaRef.current?.selectionStart || 0;
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastTwoChars = textBeforeCursor.slice(-2);
    
    if (lastTwoChars === '{{') {
      // Get cursor position for dropdown
      const textarea = textareaRef.current;
      if (textarea) {
        const rect = textarea.getBoundingClientRect();
        // Approximate position - in production would use a library
        setVariableDropdownPosition({
          top: rect.top + 60,
          left: rect.left + 20
        });
        setShowVariableDropdown(field === 'emailPrompt' ? 'email' : 'subject');
      }
    } else {
      setShowVariableDropdown(null);
    }
  };

  // Insert variable at cursor position
  const insertVariable = (variableName, field) => {
    const textareaRef = field === 'email' ? emailPromptRef : subjectPromptRef;
    const promptField = field === 'email' ? 'emailPrompt' : 'subjectPrompt';
    const currentValue = currentEmail[promptField];
    
    const textarea = textareaRef.current;
    if (textarea) {
      const cursorPos = textarea.selectionStart;
      // Remove the {{ that triggered the dropdown and insert the full variable
      const beforeCursor = currentValue.substring(0, cursorPos - 2);
      const afterCursor = currentValue.substring(cursorPos);
      const newValue = beforeCursor + '{{' + variableName + '}}' + afterCursor;
      
      updateEmailPrompt(promptField, newValue);
    }
    
    setShowVariableDropdown(null);
  };

  const addEmail = () => {
    const newId = emails.length + 1;
    setEmails([...emails, { id: newId, emailPrompt: '', subjectPrompt: '' }]);
    setTimingConfigs([...timingConfigs, { 
      mode: 'fixed_delay',
      timingType: 'relative',
      delayValue: 3, 
      delayUnit: 'days',
      specificDay: 'next_monday',
      specificTime: '10:00',
      aiOptimization: true,
      aiOptimizationType: 'basic',
      aiCustomTimingPrompt: '',
      aiMaxAdjustment: '1_week',
      aiDecidesPrompt: '',
    }]);
    setCurrentEmailIndex(emails.length);
  };

  const deleteEmail = (idx) => {
    if (emails.length <= 1) return;
    setEmails(emails.filter((_, i) => i !== idx));
    setTimingConfigs(timingConfigs.filter((_, i) => i !== idx));
    if (currentEmailIndex >= emails.length - 1) {
      setCurrentEmailIndex(Math.max(0, emails.length - 2));
    }
  };

  // Render prompt content with variable pills
  const renderPromptWithPills = (text) => {
    if (!text) return <span style={{ color: colors.latte, fontStyle: 'italic' }}>No prompt configured</span>;
    
    const parts = text.split(/(\{\{[^}]+\}\})/g);
    return parts.map((part, idx) => {
      if (part.match(/^\{\{[^}]+\}\}$/)) {
        const varName = part.slice(2, -2);
        return <VariablePill key={idx}>{varName}</VariablePill>;
      }
      return <span key={idx} style={{ whiteSpace: 'pre-wrap' }}>{part}</span>;
    });
  };

  return (
    <div style={{ 
      minHeight: '100vh', 
      backgroundColor: '#F9FAFB',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    }}>
      {/* Header */}
      <header style={{
        backgroundColor: 'white',
        borderBottom: `1px solid ${colors.foam}`,
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'none',
            border: 'none',
            color: colors.latte,
            cursor: 'pointer',
            fontSize: '14px',
            padding: '8px 12px',
            borderRadius: '8px',
          }}>
            <ArrowLeft size={18} />
            Back
          </button>
          <div>
            <h1 style={{ 
              fontSize: '20px', 
              fontWeight: '700', 
              color: colors.espresso,
              margin: 0,
              fontFamily: "'Baloo 2', cursive"
            }}>
              CRM Squirrel 🐿️
            </h1>
            <p style={{ fontSize: '13px', color: colors.latte, margin: 0 }}>
              Workflow Builder • Email Sequence
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            backgroundColor: 'white',
            border: `1px solid ${colors.latte}40`,
            borderRadius: '8px',
            color: colors.espresso,
            fontSize: '14px',
            fontWeight: '500',
            cursor: 'pointer',
          }}>
            <Settings size={16} />
            Universal Rules
          </button>
          
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            backgroundColor: 'white',
            border: `1px solid ${colors.latte}40`,
            borderRadius: '8px',
            color: colors.espresso,
            fontSize: '14px',
            fontWeight: '500',
            cursor: 'pointer'
          }}>
            <Upload size={16} />
            Import
          </button>
          
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            backgroundColor: 'white',
            border: `1px solid ${colors.latte}40`,
            borderRadius: '8px',
            color: colors.espresso,
            fontSize: '14px',
            fontWeight: '500',
            cursor: 'pointer'
          }}>
            <Download size={16} />
            Export
          </button>
          
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '10px 20px',
            background: `linear-gradient(135deg, ${colors.hyperOrange}, ${colors.orangeHover})`,
            border: 'none',
            borderRadius: '8px',
            color: 'white',
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(255, 87, 34, 0.3)',
          }}>
            <Save size={16} />
            Save
          </button>
        </div>
      </header>

      <div style={{ display: 'flex', height: 'calc(100vh - 65px)' }}>
        {/* Left Sidebar - Pipeline */}
        <aside style={{
          width: '260px',
          backgroundColor: 'white',
          borderRight: `1px solid ${colors.foam}`,
          padding: '16px',
          flexShrink: 0
        }}>
          <div style={{ 
            padding: '12px', 
            backgroundColor: colors.orangeLight, 
            borderRadius: '10px',
            border: `2px solid ${colors.hyperOrange}`,
            marginBottom: '8px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: colors.hyperOrange,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Mail size={16} color="white" />
              </div>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: colors.espresso }}>
                  Email Sequence
                </span>
                <p style={{ fontSize: '11px', color: colors.latte, margin: 0 }}>
                  {emails.length} emails configured
                </p>
              </div>
            </div>
          </div>
          <p style={{ fontSize: '11px', color: colors.latte, textAlign: 'center', marginTop: '16px' }}>
            Other components shown in sidebar...
          </p>
        </aside>

        {/* Main Content */}
        <main style={{ flex: 1, overflowY: 'auto', backgroundColor: '#F9FAFB' }}>
          <div style={{ padding: '24px', maxWidth: '900px' }}>
            
            {/* Config Panel Header */}
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'flex-start',
              marginBottom: '24px'
            }}>
              <div>
                <h2 style={{ 
                  fontSize: '24px', 
                  fontWeight: '700', 
                  color: colors.espresso,
                  margin: '0 0 6px 0',
                  fontFamily: "'Baloo 2', cursive"
                }}>
                  Email Sequence
                </h2>
                <p style={{ fontSize: '14px', color: colors.latte, margin: 0 }}>
                  Configure your follow-up email sequence
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  backgroundColor: colors.greenLight,
                  borderRadius: '20px',
                  color: colors.goGreen,
                  fontSize: '13px',
                  fontWeight: '600'
                }}>
                  <Check size={14} />
                  Configured
                </div>

                <button style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  backgroundColor: colors.redLight,
                  border: 'none',
                  borderRadius: '8px',
                  color: colors.red,
                  fontSize: '13px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}>
                  <Trash2 size={14} />
                  Delete
                </button>
              </div>
            </div>

            {/* Info Bar */}
            <div style={{
              backgroundColor: colors.foam,
              padding: '12px 16px',
              borderRadius: '10px',
              marginBottom: '20px',
              fontSize: '14px',
              color: colors.latte,
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <Mail size={16} color={colors.hyperOrange} />
              Create personalized follow-up sequences from your meeting transcripts! 📧
            </div>

            {/* Email Sequence Navigation */}
            <div style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              border: `1px solid ${colors.foam}`,
              marginBottom: '20px',
              padding: '16px 20px'
            }}>
              <div style={{
                fontSize: '11px',
                fontWeight: '600',
                color: colors.latte,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                marginBottom: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <span style={{ 
                  width: '8px', 
                  height: '8px', 
                  borderRadius: '50%', 
                  backgroundColor: colors.hyperOrange 
                }} />
                Click to edit email
              </div>

              {/* Email Tabs */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
                {emails.map((email, idx) => {
                  const isCurrent = idx === currentEmailIndex;
                  return (
                    <button
                      key={email.id}
                      onClick={() => setCurrentEmailIndex(idx)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: isCurrent ? '10px 16px' : '8px 14px',
                        borderRadius: '20px',
                        border: `2px solid ${isCurrent ? colors.hyperOrange : colors.foam}`,
                        backgroundColor: isCurrent ? colors.hyperOrange : 'white',
                        color: isCurrent ? 'white' : colors.espresso,
                        fontSize: '13px',
                        fontWeight: '600',
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                    >
                      <Mail size={14} />
                      Email {email.id}
                      {isCurrent && <Edit3 size={12} />}
                    </button>
                  );
                })}

                <button
                  onClick={addEmail}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '8px 14px',
                    borderRadius: '20px',
                    border: `2px dashed ${colors.latte}40`,
                    backgroundColor: 'transparent',
                    color: colors.latte,
                    fontSize: '13px',
                    fontWeight: '500',
                    cursor: 'pointer'
                  }}
                >
                  <Plus size={14} />
                  Add Email
                </button>
              </div>

              {/* Timeline Visualization */}
              <div style={{
                backgroundColor: colors.foam + '60',
                borderRadius: '10px',
                padding: '14px'
              }}>
                <div style={{
                  fontSize: '10px',
                  fontWeight: '600',
                  color: colors.latte,
                  textTransform: 'uppercase',
                  marginBottom: '10px'
                }}>
                  📅 Sequence Timeline
                </div>
                
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  flexWrap: 'wrap'
                }}>
                  <span style={{
                    padding: '4px 10px',
                    backgroundColor: colors.goGreen,
                    color: 'white',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: '600'
                  }}>
                    Trigger
                  </span>

                  {emails.map((email, idx) => {
                    const cfg = timingConfigs[idx];
                    const isCurrent = idx === currentEmailIndex;
                    
                    let delayText = '';
                    if (cfg.mode === 'immediate') {
                      delayText = idx === 0 ? 'immediately' : '+0';
                    } else if (cfg.mode === 'ai_decides') {
                      delayText = '🧠 AI decides';
                    } else {
                      const unit = cfg.delayUnit[0];
                      delayText = idx === 0 
                        ? `after ${cfg.delayValue}${unit}`
                        : `+${cfg.delayValue}${unit}`;
                    }

                    return (
                      <React.Fragment key={email.id}>
                        <span style={{ color: colors.latte, fontSize: '12px' }}>→</span>
                        <span style={{ 
                          fontSize: '11px', 
                          color: cfg.mode === 'ai_decides' ? colors.energyBurst : colors.latte,
                          fontWeight: cfg.mode === 'ai_decides' ? '600' : '400'
                        }}>
                          {delayText}
                        </span>
                        <span style={{ color: colors.latte, fontSize: '12px' }}>→</span>
                        <button
                          onClick={() => setCurrentEmailIndex(idx)}
                          style={{
                            padding: '4px 10px',
                            backgroundColor: isCurrent ? colors.hyperOrange : 'white',
                            color: isCurrent ? 'white' : colors.espresso,
                            border: `1px solid ${isCurrent ? colors.hyperOrange : colors.latte}40`,
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '600',
                            cursor: 'pointer'
                          }}
                        >
                          Email {email.id}
                        </button>
                      </React.Fragment>
                    );
                  })}
                </div>

                {/* AI Optimization Note */}
                {currentTiming.aiOptimization && currentTiming.mode === 'fixed_delay' && (
                  <div style={{
                    marginTop: '10px',
                    padding: '8px 12px',
                    backgroundColor: colors.energyBurst + '25',
                    borderRadius: '6px',
                    fontSize: '12px',
                    color: colors.espresso,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <Brain size={14} color={colors.energyBurst} />
                    <span>
                      <strong>AI can adjust</strong> Email {currentEmailIndex + 1}'s timing by up to {currentTiming.aiMaxAdjustment.replace('_', ' ')}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Current Email Header */}
            <div style={{
              background: `linear-gradient(135deg, ${colors.hyperOrange}, ${colors.orangeHover})`,
              borderRadius: '12px',
              padding: '16px 20px',
              marginBottom: '20px',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ fontSize: '12px', opacity: 0.9, marginBottom: '2px' }}>
                  Currently Editing
                </div>
                <div style={{ fontSize: '22px', fontWeight: '700', fontFamily: "'Baloo 2', cursive" }}>
                  Email {currentEmailIndex + 1}
                </div>
              </div>
              {emails.length > 1 && (
                <button
                  onClick={() => deleteEmail(currentEmailIndex)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 14px',
                    backgroundColor: 'rgba(255,255,255,0.2)',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    fontSize: '13px',
                    fontWeight: '500',
                    cursor: 'pointer'
                  }}
                >
                  <Trash2 size={14} />
                  Delete Email
                </button>
              )}
            </div>

            {/* AI Prompt Configuration Section */}
            <CollapsibleSection
              icon={Code}
              title="AI Prompt Configuration"
              isOpen={promptExpanded}
              onToggle={() => setPromptExpanded(!promptExpanded)}
            >
              {/* Email Body Prompt */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  marginBottom: '12px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      backgroundColor: colors.orangeLight,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      <FileText size={14} color={colors.hyperOrange} />
                    </div>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: colors.espresso }}>
                      Email Body Prompt
                    </span>
                    <span style={{
                      padding: '2px 8px',
                      backgroundColor: colors.hyperOrange,
                      color: 'white',
                      fontSize: '10px',
                      fontWeight: '600',
                      borderRadius: '10px'
                    }}>
                      🥜 Required
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => setIsEditingEmailPrompt(!isEditingEmailPrompt)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        backgroundColor: 'white',
                        border: `1px solid ${colors.latte}40`,
                        borderRadius: '6px',
                        color: colors.espresso,
                        fontSize: '13px',
                        fontWeight: '500',
                        cursor: 'pointer'
                      }}
                    >
                      <Edit3 size={14} />
                      Edit
                    </button>
                    <button
                      onClick={() => handleCopy('email')}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        backgroundColor: copiedEmailPrompt ? colors.greenLight : 'white',
                        border: `1px solid ${copiedEmailPrompt ? colors.goGreen : colors.latte}40`,
                        borderRadius: '6px',
                        color: copiedEmailPrompt ? colors.goGreen : colors.espresso,
                        fontSize: '13px',
                        fontWeight: '500',
                        cursor: 'pointer'
                      }}
                    >
                      {copiedEmailPrompt ? <Check size={14} /> : <Copy size={14} />}
                      {copiedEmailPrompt ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                </div>

                {/* Prompt Display/Editor */}
                <div style={{
                  backgroundColor: '#FAFAFA',
                  border: `2px solid ${isEditingEmailPrompt ? colors.hyperOrange : colors.foam}`,
                  borderRadius: '10px',
                  padding: '16px',
                  fontFamily: "'Space Mono', monospace",
                  fontSize: '13px',
                  lineHeight: '1.8',
                  color: colors.espresso
                }}>
                  {isEditingEmailPrompt ? (
                    <textarea
                      ref={emailPromptRef}
                      value={currentEmail.emailPrompt}
                      onChange={(e) => handlePromptChange('emailPrompt', e.target.value, emailPromptRef)}
                      style={{
                        width: '100%',
                        minHeight: '200px',
                        backgroundColor: 'white',
                        border: 'none',
                        fontFamily: "'Space Mono', monospace",
                        fontSize: '13px',
                        lineHeight: '1.8',
                        color: colors.espresso,
                        resize: 'vertical',
                        outline: 'none',
                        padding: '0'
                      }}
                      placeholder="Write your email prompt here. Use {{variable_name}} to insert variables."
                    />
                  ) : (
                    <div>{renderPromptWithPills(currentEmail.emailPrompt)}</div>
                  )}
                </div>

                <p style={{ 
                  fontSize: '12px', 
                  color: colors.latte, 
                  marginTop: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}>
                  <Sparkles size={12} color={colors.hyperOrange} />
                  Type <code style={{ 
                    backgroundColor: colors.foam, 
                    padding: '2px 6px', 
                    borderRadius: '4px',
                    fontFamily: 'monospace'
                  }}>{'{{'}</code> to insert variables from previous components
                </p>
              </div>

              {/* Subject Line Prompt */}
              <div>
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  marginBottom: '12px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      backgroundColor: colors.orangeLight,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      <Target size={14} color={colors.hyperOrange} />
                    </div>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: colors.espresso }}>
                      Subject Line Prompt
                    </span>
                    <span style={{
                      padding: '2px 8px',
                      backgroundColor: colors.latte + '30',
                      color: colors.latte,
                      fontSize: '10px',
                      fontWeight: '600',
                      borderRadius: '10px'
                    }}>
                      Optional
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => setIsEditingSubjectPrompt(!isEditingSubjectPrompt)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        backgroundColor: 'white',
                        border: `1px solid ${colors.latte}40`,
                        borderRadius: '6px',
                        color: colors.espresso,
                        fontSize: '13px',
                        fontWeight: '500',
                        cursor: 'pointer'
                      }}
                    >
                      <Edit3 size={14} />
                      Edit
                    </button>
                    <button
                      onClick={() => handleCopy('subject')}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        backgroundColor: copiedSubjectPrompt ? colors.greenLight : 'white',
                        border: `1px solid ${copiedSubjectPrompt ? colors.goGreen : colors.latte}40`,
                        borderRadius: '6px',
                        color: copiedSubjectPrompt ? colors.goGreen : colors.espresso,
                        fontSize: '13px',
                        fontWeight: '500',
                        cursor: 'pointer'
                      }}
                    >
                      {copiedSubjectPrompt ? <Check size={14} /> : <Copy size={14} />}
                      {copiedSubjectPrompt ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                </div>

                <div style={{
                  backgroundColor: '#FAFAFA',
                  border: `2px solid ${isEditingSubjectPrompt ? colors.hyperOrange : colors.foam}`,
                  borderRadius: '10px',
                  padding: '16px',
                  fontFamily: "'Space Mono', monospace",
                  fontSize: '13px',
                  lineHeight: '1.8',
                  color: colors.espresso
                }}>
                  {isEditingSubjectPrompt ? (
                    <textarea
                      ref={subjectPromptRef}
                      value={currentEmail.subjectPrompt}
                      onChange={(e) => handlePromptChange('subjectPrompt', e.target.value, subjectPromptRef)}
                      style={{
                        width: '100%',
                        minHeight: '80px',
                        backgroundColor: 'white',
                        border: 'none',
                        fontFamily: "'Space Mono', monospace",
                        fontSize: '13px',
                        lineHeight: '1.8',
                        color: colors.espresso,
                        resize: 'vertical',
                        outline: 'none',
                        padding: '0'
                      }}
                      placeholder="Write your subject line prompt here..."
                    />
                  ) : (
                    <div>{renderPromptWithPills(currentEmail.subjectPrompt)}</div>
                  )}
                </div>
              </div>

              {/* Save Configuration Button */}
              <button style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '14px 20px',
                marginTop: '20px',
                background: `linear-gradient(135deg, ${colors.hyperOrange}, ${colors.orangeHover})`,
                border: 'none',
                borderRadius: '10px',
                color: 'white',
                fontSize: '15px',
                fontWeight: '600',
                cursor: 'pointer',
                boxShadow: '0 2px 8px rgba(255, 87, 34, 0.3)',
              }}>
                <Save size={18} />
                Save Configuration
              </button>
            </CollapsibleSection>


            {/* Send Timing Section */}
            <CollapsibleSection
              icon={Clock}
              title="Send Timing"
              isOpen={timingExpanded}
              onToggle={() => setTimingExpanded(!timingExpanded)}
            >
              <p style={{ 
                fontSize: '13px', 
                color: colors.latte, 
                marginBottom: '16px'
              }}>
                {currentEmailIndex === 0 
                  ? "When should this email be sent after the workflow triggers?"
                  : `When should this email be sent after Email ${currentEmailIndex}?`
                }
              </p>

              {/* Timing Mode Cards */}
              <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
                <TimingModeCard
                  isSelected={currentTiming.mode === 'immediate'}
                  icon={Zap}
                  title="Immediate"
                  description="Send right away"
                  onClick={() => updateTimingConfig('mode', 'immediate')}
                />
                <TimingModeCard
                  isSelected={currentTiming.mode === 'fixed_delay'}
                  icon={Timer}
                  title="Fixed Delay"
                  description="Set base time, AI can optimize"
                  onClick={() => updateTimingConfig('mode', 'fixed_delay')}
                />
                <TimingModeCard
                  isSelected={currentTiming.mode === 'ai_decides'}
                  icon={Brain}
                  title="AI Decides"
                  description="100% AI controlled"
                  recommended={true}
                  onClick={() => updateTimingConfig('mode', 'ai_decides')}
                />
              </div>

              {/* Fixed Delay Config */}
              {currentTiming.mode === 'fixed_delay' && (
                <div style={{
                  backgroundColor: 'white',
                  borderRadius: '12px',
                  border: `2px solid ${colors.foam}`,
                  marginBottom: '16px',
                  overflow: 'hidden'
                }}>
                  {/* Timing Type Tabs */}
                  <div style={{
                    display: 'flex',
                    borderBottom: `1px solid ${colors.foam}`
                  }}>
                    <button
                      onClick={() => updateTimingConfig('timingType', 'relative')}
                      style={{
                        flex: 1,
                        padding: '14px 20px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        backgroundColor: currentTiming.timingType === 'relative' ? 'white' : colors.foam + '60',
                        border: 'none',
                        borderBottom: currentTiming.timingType === 'relative' 
                          ? `3px solid ${colors.hyperOrange}` 
                          : '3px solid transparent',
                        cursor: 'pointer',
                        color: currentTiming.timingType === 'relative' ? colors.espresso : colors.latte,
                        fontSize: '14px',
                        fontWeight: '600',
                        transition: 'all 0.2s'
                      }}
                    >
                      <Timer size={18} color={currentTiming.timingType === 'relative' ? colors.hyperOrange : colors.latte} />
                      Relative Time
                    </button>
                    <button
                      onClick={() => updateTimingConfig('timingType', 'specific_day')}
                      style={{
                        flex: 1,
                        padding: '14px 20px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        backgroundColor: currentTiming.timingType === 'specific_day' ? 'white' : colors.foam + '60',
                        border: 'none',
                        borderBottom: currentTiming.timingType === 'specific_day' 
                          ? `3px solid ${colors.hyperOrange}` 
                          : '3px solid transparent',
                        cursor: 'pointer',
                        color: currentTiming.timingType === 'specific_day' ? colors.espresso : colors.latte,
                        fontSize: '14px',
                        fontWeight: '600',
                        transition: 'all 0.2s'
                      }}
                    >
                      <Calendar size={18} color={currentTiming.timingType === 'specific_day' ? colors.hyperOrange : colors.latte} />
                      Specific Day
                    </button>
                  </div>

                  {/* Timing Content */}
                  <div style={{ padding: '20px' }}>
                    <label style={{ 
                      fontSize: '13px', 
                      fontWeight: '600', 
                      color: colors.espresso,
                      display: 'block',
                      marginBottom: '12px'
                    }}>
                      {currentEmailIndex === 0 ? 'Delay after trigger:' : `Delay after Email ${currentEmailIndex}:`}
                    </label>

                    {currentTiming.timingType === 'relative' ? (
                      /* Relative Time Input */
                      <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '12px',
                        padding: '16px',
                        backgroundColor: colors.foam + '40',
                        borderRadius: '10px'
                      }}>
                        <input
                          type="number"
                          value={currentTiming.delayValue}
                          onChange={(e) => updateTimingConfig('delayValue', parseInt(e.target.value) || 0)}
                          min="0"
                          style={{
                            width: '90px',
                            padding: '12px 14px',
                            fontSize: '16px',
                            fontWeight: '600',
                            border: `2px solid ${colors.latte}30`,
                            borderRadius: '10px',
                            textAlign: 'center',
                            color: colors.espresso,
                            backgroundColor: 'white'
                          }}
                        />
                        <select
                          value={currentTiming.delayUnit}
                          onChange={(e) => updateTimingConfig('delayUnit', e.target.value)}
                          style={{
                            padding: '12px 16px',
                            fontSize: '14px',
                            fontWeight: '500',
                            border: `2px solid ${colors.latte}30`,
                            borderRadius: '10px',
                            backgroundColor: 'white',
                            color: colors.espresso,
                            cursor: 'pointer',
                            minWidth: '120px'
                          }}
                        >
                          <option value="minutes">Minutes</option>
                          <option value="hours">Hours</option>
                          <option value="days">Days</option>
                        </select>
                        <span style={{ 
                          fontSize: '13px', 
                          color: colors.latte,
                          marginLeft: '8px'
                        }}>
                          after {currentEmailIndex === 0 ? 'trigger' : `Email ${currentEmailIndex}`}
                        </span>
                      </div>
                    ) : (
                      /* Specific Day Input */
                      <div style={{
                        padding: '16px',
                        backgroundColor: colors.foam + '40',
                        borderRadius: '10px'
                      }}>
                        <div style={{ marginBottom: '16px' }}>
                          <label style={{ 
                            fontSize: '12px', 
                            fontWeight: '600', 
                            color: colors.latte,
                            display: 'block',
                            marginBottom: '8px',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px'
                          }}>
                            Send on
                          </label>
                          <select
                            value={currentTiming.specificDay}
                            onChange={(e) => updateTimingConfig('specificDay', e.target.value)}
                            style={{
                              width: '100%',
                              padding: '14px 16px',
                              fontSize: '15px',
                              fontWeight: '500',
                              border: `2px solid ${colors.latte}30`,
                              borderRadius: '10px',
                              backgroundColor: 'white',
                              color: colors.espresso,
                              cursor: 'pointer'
                            }}
                          >
                            <option value="next_monday">Next Monday</option>
                            <option value="next_tuesday">Next Tuesday</option>
                            <option value="next_wednesday">Next Wednesday</option>
                            <option value="next_thursday">Next Thursday</option>
                            <option value="next_friday">Next Friday</option>
                            <option value="first_of_month">First of Next Month</option>
                            <option value="end_of_week">End of This Week</option>
                          </select>
                        </div>

                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '12px'
                        }}>
                          <label style={{ 
                            fontSize: '12px', 
                            fontWeight: '600', 
                            color: colors.latte,
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px'
                          }}>
                            at
                          </label>
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '10px 14px',
                            backgroundColor: 'white',
                            border: `2px solid ${colors.latte}30`,
                            borderRadius: '10px'
                          }}>
                            <Clock size={16} color={colors.latte} />
                            <input
                              type="time"
                              value={currentTiming.specificTime}
                              onChange={(e) => updateTimingConfig('specificTime', e.target.value)}
                              style={{
                                border: 'none',
                                fontSize: '15px',
                                fontWeight: '500',
                                color: colors.espresso,
                                outline: 'none',
                                backgroundColor: 'transparent'
                              }}
                            />
                          </div>
                          <span style={{ 
                            fontSize: '12px', 
                            color: colors.latte,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}>
                            (recipient's timezone)
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Helpful hint */}
                    <p style={{
                      fontSize: '12px',
                      color: colors.latte,
                      marginTop: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}>
                      <Sparkles size={12} color={colors.energyBurst} />
                      {currentTiming.timingType === 'relative' 
                        ? 'Perfect for time-sensitive follow-ups where consistency matters'
                        : 'Great for scheduling around specific days like "Next Monday" or "End of Week"'
                      }
                    </p>
                  </div>
                </div>
              )}

              {/* AI Decides Info */}
              {currentTiming.mode === 'ai_decides' && (
                <div style={{
                  background: `linear-gradient(135deg, ${colors.energyBurst}20, ${colors.foam})`,
                  border: `1px solid ${colors.energyBurst}50`,
                  borderRadius: '10px',
                  padding: '16px',
                  marginBottom: '16px'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    marginBottom: '12px'
                  }}>
                    <Brain size={20} color={colors.energyBurst} />
                    <span style={{ fontSize: '14px', fontWeight: '600', color: colors.espresso }}>
                      100% AI Controlled Timing
                    </span>
                  </div>
                  <p style={{ fontSize: '13px', color: colors.latte, margin: '0 0 16px 0', lineHeight: '1.5' }}>
                    AI will analyze the meeting transcript and determine the optimal time to send this email. 
                    No base timing is set - AI has full control based on context.
                  </p>

                  {/* Built-in AI Detection */}
                  <div style={{
                    backgroundColor: 'white',
                    borderRadius: '8px',
                    padding: '12px',
                    marginBottom: '16px'
                  }}>
                    <div style={{ fontSize: '12px', fontWeight: '600', color: colors.espresso, marginBottom: '8px' }}>
                      🧠 Default AI considerations:
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {['Urgency signals', 'OOO / Travel mentions', 'Decision timeline', 'Meeting follow-up norms', 'Timezone optimization'].map(item => (
                        <span key={item} style={{
                          backgroundColor: colors.energyBurst + '20',
                          color: colors.espresso,
                          padding: '4px 10px',
                          borderRadius: '12px',
                          fontSize: '11px',
                          fontWeight: '500'
                        }}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Optional Custom Prompt */}
                  <div>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'space-between',
                      marginBottom: '8px'
                    }}>
                      <label style={{ 
                        fontSize: '13px', 
                        fontWeight: '600', 
                        color: colors.espresso,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <Edit3 size={14} color={colors.energyBurst} />
                        Custom AI Instructions
                        <span style={{ 
                          fontSize: '11px', 
                          fontWeight: '500', 
                          color: colors.latte,
                          backgroundColor: colors.foam,
                          padding: '2px 8px',
                          borderRadius: '10px'
                        }}>
                          Optional
                        </span>
                      </label>
                    </div>
                    <textarea
                      value={currentTiming.aiDecidesPrompt}
                      onChange={(e) => updateTimingConfig('aiDecidesPrompt', e.target.value)}
                      placeholder="Add specific instructions to guide AI timing decisions...

Example: If the prospect mentioned they are traveling, wait until they return. If high urgency was expressed, send within 24 hours."
                      style={{
                        width: '100%',
                        minHeight: '100px',
                        padding: '12px 14px',
                        fontSize: '13px',
                        lineHeight: '1.5',
                        border: `1px solid ${colors.latte}30`,
                        borderRadius: '8px',
                        backgroundColor: 'white',
                        color: colors.espresso,
                        resize: 'vertical',
                        fontFamily: 'inherit'
                      }}
                    />
                    <p style={{ 
                      fontSize: '11px', 
                      color: colors.latte, 
                      marginTop: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <Sparkles size={10} color={colors.energyBurst} />
                      Leave empty to use default AI logic, or add custom instructions to guide timing decisions
                    </p>
                  </div>
                </div>
              )}

              {/* AI Optimization Toggle (for Fixed Delay) */}
              {currentTiming.mode === 'fixed_delay' && (
                <div style={{
                  backgroundColor: currentTiming.aiOptimization ? colors.greenLight : colors.foam,
                  border: `1px solid ${currentTiming.aiOptimization ? colors.goGreen + '40' : colors.latte + '20'}`,
                  borderRadius: '10px',
                  padding: '16px'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: currentTiming.aiOptimization ? '16px' : 0
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Brain size={18} color={currentTiming.aiOptimization ? colors.goGreen : colors.latte} />
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: '600', color: colors.espresso }}>
                          AI Timing Optimization
                        </div>
                        <div style={{ fontSize: '12px', color: colors.latte, marginTop: '2px' }}>
                          {currentTiming.aiOptimization 
                            ? 'AI can adjust timing based on meeting context'
                            : 'Disabled - email sends at exact scheduled time'
                          }
                        </div>
                      </div>
                    </div>
                    <ToggleSwitch 
                      checked={currentTiming.aiOptimization}
                      onChange={(val) => updateTimingConfig('aiOptimization', val)}
                    />
                  </div>

                  {currentTiming.aiOptimization && (
                    <>
                      {/* Basic vs Custom Toggle */}
                      <div style={{
                        display: 'flex',
                        backgroundColor: 'white',
                        borderRadius: '8px',
                        padding: '4px',
                        marginBottom: '16px'
                      }}>
                        <button
                          onClick={() => updateTimingConfig('aiOptimizationType', 'basic')}
                          style={{
                            flex: 1,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '6px',
                            padding: '10px 16px',
                            backgroundColor: currentTiming.aiOptimizationType === 'basic' ? colors.goGreen : 'transparent',
                            border: 'none',
                            borderRadius: '6px',
                            color: currentTiming.aiOptimizationType === 'basic' ? 'white' : colors.latte,
                            fontSize: '13px',
                            fontWeight: '600',
                            cursor: 'pointer',
                            transition: 'all 0.2s'
                          }}
                        >
                          <Zap size={14} />
                          Basic Optimization
                        </button>
                        <button
                          onClick={() => updateTimingConfig('aiOptimizationType', 'custom')}
                          style={{
                            flex: 1,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '6px',
                            padding: '10px 16px',
                            backgroundColor: currentTiming.aiOptimizationType === 'custom' ? colors.goGreen : 'transparent',
                            border: 'none',
                            borderRadius: '6px',
                            color: currentTiming.aiOptimizationType === 'custom' ? 'white' : colors.latte,
                            fontSize: '13px',
                            fontWeight: '600',
                            cursor: 'pointer',
                            transition: 'all 0.2s'
                          }}
                        >
                          <Edit3 size={14} />
                          Custom Prompt
                        </button>
                      </div>

                      {/* Basic Optimization Content */}
                      {currentTiming.aiOptimizationType === 'basic' && (
                        <div style={{
                          backgroundColor: 'white',
                          borderRadius: '8px',
                          padding: '12px',
                          marginBottom: '12px'
                        }}>
                          <div style={{ fontSize: '12px', fontWeight: '600', color: colors.espresso, marginBottom: '8px' }}>
                            🧠 Built-in detection:
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {['Travel / OOO plans', 'Urgency signals', 'Long decision cycles', 'Mentioned deadlines', 'Timezone awareness'].map(item => (
                              <span key={item} style={{
                                backgroundColor: colors.greenLight,
                                color: colors.espresso,
                                padding: '4px 10px',
                                borderRadius: '12px',
                                fontSize: '11px',
                                fontWeight: '500'
                              }}>
                                ✓ {item}
                              </span>
                            ))}
                          </div>
                          <p style={{ 
                            fontSize: '11px', 
                            color: colors.latte, 
                            margin: '10px 0 0 0',
                            lineHeight: '1.4'
                          }}>
                            AI will use these built-in signals to adjust your scheduled timing when context suggests it
                          </p>
                        </div>
                      )}

                      {/* Custom Prompt Content */}
                      {currentTiming.aiOptimizationType === 'custom' && (
                        <div style={{ marginBottom: '12px' }}>
                          <label style={{ 
                            fontSize: '13px', 
                            fontWeight: '600', 
                            color: colors.espresso,
                            display: 'block',
                            marginBottom: '8px'
                          }}>
                            Custom Timing Instructions
                          </label>
                          <textarea
                            value={currentTiming.aiCustomTimingPrompt}
                            onChange={(e) => updateTimingConfig('aiCustomTimingPrompt', e.target.value)}
                            placeholder="Add specific instructions for when AI should adjust timing...

Example: If the prospect mentioned Q1 budget approval, delay until January. If they're going on vacation, wait until they return + 2 days."
                            style={{
                              width: '100%',
                              minHeight: '100px',
                              padding: '12px 14px',
                              fontSize: '13px',
                              lineHeight: '1.5',
                              border: `1px solid ${colors.goGreen}40`,
                              borderRadius: '8px',
                              backgroundColor: 'white',
                              color: colors.espresso,
                              resize: 'vertical',
                              fontFamily: 'inherit'
                            }}
                          />
                          <p style={{ 
                            fontSize: '11px', 
                            color: colors.latte, 
                            marginTop: '6px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}>
                            <Sparkles size={10} color={colors.goGreen} />
                            Your custom rules override the default timing when conditions are met
                          </p>
                        </div>
                      )}

                      {/* Maximum Adjustment (shown for both) */}
                      <div>
                        <label style={{ 
                          fontSize: '13px', 
                          fontWeight: '600', 
                          color: colors.espresso,
                          display: 'block',
                          marginBottom: '6px'
                        }}>
                          Maximum adjustment from scheduled time
                        </label>
                        <select
                          value={currentTiming.aiMaxAdjustment}
                          onChange={(e) => updateTimingConfig('aiMaxAdjustment', e.target.value)}
                          style={{
                            padding: '10px 14px',
                            fontSize: '14px',
                            border: `1px solid ${colors.latte}40`,
                            borderRadius: '8px',
                            backgroundColor: 'white',
                            cursor: 'pointer'
                          }}
                        >
                          <option value="1_day">± 1 day</option>
                          <option value="3_days">± 3 days</option>
                          <option value="1_week">± 1 week</option>
                          <option value="2_weeks">± 2 weeks</option>
                          <option value="1_month">± 1 month</option>
                        </select>
                        <p style={{ 
                          fontSize: '11px', 
                          color: colors.latte, 
                          marginTop: '6px' 
                        }}>
                          AI won't move the email beyond this range from your scheduled time
                        </p>
                      </div>
                    </>
                  )}
                </div>
              )}
            </CollapsibleSection>

            {/* Delivery Settings Section */}
            <CollapsibleSection
              icon={Shield}
              title="Delivery Settings"
              isOpen={deliveryExpanded}
              onToggle={() => setDeliveryExpanded(!deliveryExpanded)}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <Checkbox
                  checked={deliverySettings.businessHoursOnly}
                  onChange={(val) => setDeliverySettings({...deliverySettings, businessHoursOnly: val})}
                  label="Send during business hours only"
                  description="Emails will only be sent between your configured business hours"
                />

                {deliverySettings.businessHoursOnly && (
                  <div style={{ 
                    display: 'flex', 
                    gap: '12px', 
                    marginLeft: '32px',
                    marginTop: '8px',
                    marginBottom: '8px'
                  }}>
                    <div>
                      <label style={{ fontSize: '12px', color: colors.latte, display: 'block', marginBottom: '4px' }}>
                        Start
                      </label>
                      <input
                        type="time"
                        value={deliverySettings.businessStart}
                        onChange={(e) => setDeliverySettings({...deliverySettings, businessStart: e.target.value})}
                        style={{
                          padding: '8px 12px',
                          fontSize: '14px',
                          border: `1px solid ${colors.latte}40`,
                          borderRadius: '8px'
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', color: colors.latte, display: 'block', marginBottom: '4px' }}>
                        End
                      </label>
                      <input
                        type="time"
                        value={deliverySettings.businessEnd}
                        onChange={(e) => setDeliverySettings({...deliverySettings, businessEnd: e.target.value})}
                        style={{
                          padding: '8px 12px',
                          fontSize: '14px',
                          border: `1px solid ${colors.latte}40`,
                          borderRadius: '8px'
                        }}
                      />
                    </div>
                  </div>
                )}

                <Checkbox
                  checked={deliverySettings.respectTimezone}
                  onChange={(val) => setDeliverySettings({...deliverySettings, respectTimezone: val})}
                  label="Respect recipient's timezone"
                  description="Adjust send times based on the recipient's local timezone"
                />

                <Checkbox
                  checked={deliverySettings.avoidWeekends}
                  onChange={(val) => setDeliverySettings({...deliverySettings, avoidWeekends: val})}
                  label="Avoid weekends"
                  description="Push weekend sends to the next Monday"
                />
              </div>
            </CollapsibleSection>

            {/* Skip Conditions Section */}
            <CollapsibleSection
              icon={SkipForward}
              title="Skip Conditions"
              isOpen={skipExpanded}
              onToggle={() => setSkipExpanded(!skipExpanded)}
            >
              <p style={{ 
                fontSize: '13px', 
                color: colors.latte, 
                marginBottom: '12px'
              }}>
                Don't send this email if:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <Checkbox
                  checked={skipConditions.ifResponded}
                  onChange={(val) => setSkipConditions({...skipConditions, ifResponded: val})}
                  label="Recipient already responded"
                />

                <Checkbox
                  checked={skipConditions.ifMeetingScheduled}
                  onChange={(val) => setSkipConditions({...skipConditions, ifMeetingScheduled: val})}
                  label="Meeting already scheduled"
                />

                <Checkbox
                  checked={skipConditions.ifBounced}
                  onChange={(val) => setSkipConditions({...skipConditions, ifBounced: val})}
                  label="Previous email bounced"
                />

                <Checkbox
                  checked={skipConditions.ifDealStageChanged}
                  onChange={(val) => setSkipConditions({...skipConditions, ifDealStageChanged: val})}
                  label="Deal reached specific stage"
                />

                {skipConditions.ifDealStageChanged && (
                  <div style={{ marginLeft: '32px', marginTop: '8px' }}>
                    <select
                      value={skipConditions.dealStage}
                      onChange={(e) => setSkipConditions({...skipConditions, dealStage: e.target.value})}
                      style={{
                        padding: '10px 14px',
                        fontSize: '14px',
                        border: `1px solid ${colors.latte}40`,
                        borderRadius: '8px',
                        backgroundColor: 'white',
                        cursor: 'pointer',
                        minWidth: '200px'
                      }}
                    >
                      <option value="">Select stage...</option>
                      <option value="won">Won</option>
                      <option value="lost">Lost</option>
                      <option value="qualified">Qualified</option>
                      <option value="proposal">Proposal Sent</option>
                    </select>
                  </div>
                )}
              </div>
            </CollapsibleSection>

            {/* Test Component Section - Moved to bottom */}
            <div style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              border: `1px solid ${colors.foam}`,
              marginBottom: '20px',
              overflow: 'hidden'
            }}>
              <div style={{ 
                padding: '16px 20px',
                borderBottom: `1px solid ${colors.foam}`,
                backgroundColor: colors.foam + '40'
              }}>
                <h3 style={{ 
                  fontSize: '14px', 
                  fontWeight: '600', 
                  color: colors.espresso,
                  margin: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <Play size={16} color={colors.hyperOrange} />
                  Test Component
                </h3>
                <p style={{ fontSize: '12px', color: colors.latte, margin: '4px 0 0 0' }}>
                  Let's make sure your email generation is working perfectly! 🧪
                </p>
              </div>

              <div style={{ padding: '20px' }}>
                <label style={{ 
                  fontSize: '13px', 
                  fontWeight: '600', 
                  color: colors.espresso,
                  display: 'block',
                  marginBottom: '8px'
                }}>
                  Select Test Data
                </label>
                <select
                  value={testDataSource}
                  onChange={(e) => setTestDataSource(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '14px',
                    border: `1px solid ${colors.latte}30`,
                    borderRadius: '8px',
                    backgroundColor: 'white',
                    color: colors.espresso,
                    marginBottom: '16px',
                    cursor: 'pointer'
                  }}
                >
                  <option value="mock">Use default mock data</option>
                  <option value="pipedrive1">Pipedrive Demo (Dec 22, 2025 • 20 min)</option>
                  <option value="pipedrive2">Andy Lockwood Call (Dec 24, 2025 • 27 min)</option>
                </select>

                <button 
                  onClick={() => setShowTestResults(true)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    padding: '12px 20px',
                    background: `linear-gradient(135deg, ${colors.hyperOrange}, ${colors.orangeHover})`,
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(255, 87, 34, 0.25)',
                  }}
                >
                  <Play size={18} />
                  Run Test
                </button>

                {/* Test Results */}
                {showTestResults && (
                  <div style={{ marginTop: '20px' }}>
                    <div style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      marginBottom: '12px'
                    }}>
                      <h4 style={{ 
                        fontSize: '14px', 
                        fontWeight: '600', 
                        color: colors.espresso,
                        margin: 0
                      }}>
                        Test Results
                      </h4>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        {/* Formatted/JSON Toggle */}
                        <div style={{
                          display: 'flex',
                          backgroundColor: colors.foam,
                          borderRadius: '6px',
                          padding: '2px'
                        }}>
                          <button
                            onClick={() => setResultsViewMode('formatted')}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                              padding: '5px 10px',
                              backgroundColor: resultsViewMode === 'formatted' ? 'white' : 'transparent',
                              border: 'none',
                              borderRadius: '4px',
                              color: resultsViewMode === 'formatted' ? colors.hyperOrange : colors.latte,
                              fontSize: '12px',
                              fontWeight: '600',
                              cursor: 'pointer',
                              boxShadow: resultsViewMode === 'formatted' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
                            }}
                          >
                            <AlignLeft size={14} />
                            Formatted
                          </button>
                          <button
                            onClick={() => setResultsViewMode('json')}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                              padding: '5px 10px',
                              backgroundColor: resultsViewMode === 'json' ? 'white' : 'transparent',
                              border: 'none',
                              borderRadius: '4px',
                              color: resultsViewMode === 'json' ? colors.hyperOrange : colors.latte,
                              fontSize: '12px',
                              fontWeight: '600',
                              cursor: 'pointer',
                              boxShadow: resultsViewMode === 'json' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
                            }}
                          >
                            <Code size={14} />
                            JSON
                          </button>
                        </div>

                        <button
                          onClick={handleCopyResults}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '6px 12px',
                            backgroundColor: copiedResults ? colors.greenLight : 'white',
                            border: `1px solid ${copiedResults ? colors.goGreen : colors.latte}40`,
                            borderRadius: '6px',
                            color: copiedResults ? colors.goGreen : colors.espresso,
                            fontSize: '12px',
                            fontWeight: '500',
                            cursor: 'pointer'
                          }}
                        >
                          {copiedResults ? <Check size={14} /> : <Copy size={14} />}
                          {copiedResults ? 'Copied!' : 'Copy'}
                        </button>
                      </div>
                    </div>

                    {/* Success Badge */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '10px 14px',
                      backgroundColor: colors.greenLight,
                      borderRadius: '8px 8px 0 0',
                      border: `1px solid ${colors.goGreen}30`,
                      borderBottom: 'none'
                    }}>
                      <CheckCircle size={16} color={colors.goGreen} />
                      <span style={{ fontSize: '13px', fontWeight: '600', color: colors.goGreen }}>
                        Email Generated Successfully
                      </span>
                      <span style={{ fontSize: '12px', color: colors.latte, marginLeft: 'auto' }}>
                        Holy acorns, it worked! 🎉
                      </span>
                    </div>

                    {/* Results Content */}
                    {resultsViewMode === 'formatted' ? (
                      <div style={{
                        backgroundColor: 'white',
                        borderRadius: '0 0 8px 8px',
                        border: `1px solid ${colors.foam}`,
                        borderTop: 'none',
                        padding: '20px'
                      }}>
                        {/* Subject Line */}
                        <div style={{ marginBottom: '20px' }}>
                          <div style={{ 
                            fontSize: '12px', 
                            fontWeight: '600', 
                            color: colors.latte,
                            textTransform: 'uppercase',
                            marginBottom: '6px'
                          }}>
                            Subject Line
                          </div>
                          <div style={{
                            padding: '12px 16px',
                            backgroundColor: colors.foam,
                            borderRadius: '8px',
                            fontSize: '14px',
                            fontWeight: '600',
                            color: colors.espresso
                          }}>
                            Following up on our Pipedrive integration discussion
                          </div>
                        </div>

                        {/* Email Body */}
                        <div>
                          <div style={{ 
                            fontSize: '12px', 
                            fontWeight: '600', 
                            color: colors.latte,
                            textTransform: 'uppercase',
                            marginBottom: '6px'
                          }}>
                            Email Body
                          </div>
                          <div style={{
                            padding: '16px',
                            backgroundColor: colors.foam + '60',
                            borderRadius: '8px',
                            fontSize: '14px',
                            lineHeight: '1.7',
                            color: colors.espresso
                          }}>
                            <p style={{ margin: '0 0 12px 0' }}>Hi Evan,</p>
                            <p style={{ margin: '0 0 12px 0' }}>
                              Great speaking with you today! I wanted to follow up on our conversation about the Pipedrive integration and the challenges you mentioned with your current workflow.
                            </p>
                            <p style={{ margin: '0 0 12px 0' }}>
                              <strong>Key points we discussed:</strong>
                            </p>
                            <ul style={{ margin: '0 0 12px 0', paddingLeft: '20px' }}>
                              <li>Your trial subscription expired, preventing work on the project</li>
                              <li>Difficulty balancing work during holiday periods</li>
                            </ul>
                            <p style={{ margin: '0 0 12px 0' }}>
                              <strong>Next steps:</strong> Let's reconnect after the holidays to dive deeper into the integration requirements.
                            </p>
                            <p style={{ margin: 0 }}>
                              Looking forward to continuing our conversation!<br /><br />
                              Best,<br />
                              Joshua
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{
                        backgroundColor: colors.espresso,
                        borderRadius: '0 0 8px 8px',
                        padding: '16px',
                        fontFamily: "'Space Mono', monospace",
                        fontSize: '12px',
                        lineHeight: '1.6',
                        color: colors.foam,
                        overflowX: 'auto'
                      }}>
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
{`{
  "status": "success",
  "email": {
    "subject": "Following up on our Pipedrive integration discussion",
    "body": "Hi Evan,\\n\\nGreat speaking with you today! I wanted to follow up on our conversation...",
    "recipient": "evan@example.com",
    "generated_at": "2025-12-27T10:30:00Z"
  },
  "variables_used": [
    "key_points",
    "action_items", 
    "next_steps",
    "meeting_title"
  ],
  "acorns_used": 3
}`}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div style={{
              textAlign: 'center',
              padding: '24px',
              color: colors.latte,
              fontSize: '13px'
            }}>
              🐿️ Powered by caffeinated squirrel intelligence ☕
            </div>
          </div>
        </main>
      </div>

      {/* Variable Dropdown - appears when typing {{ in prompt editors */}
      {showVariableDropdown && (
        <VariableDropdown
          variables={availableVariables}
          onSelect={(varName) => insertVariable(varName, showVariableDropdown)}
          onClose={() => setShowVariableDropdown(null)}
          position={variableDropdownPosition}
        />
      )}

      {/* Google Fonts */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Inter:wght@400;500;600;700&family=Space+Mono&display=swap');
      `}</style>
    </div>
  );
}
