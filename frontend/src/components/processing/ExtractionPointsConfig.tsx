import React, { useState, useRef, useEffect } from 'react'
import { Plus, Trash2, AlertCircle, User, Info, DollarSign, Calendar, ArrowRight, Building2, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'

interface ExtractionPoint {
  name: string
  description: string
  required: boolean
  type: 'string' | 'array' | 'number' | 'boolean'
}

interface ExtractionPointsConfigProps {
  value: ExtractionPoint[]
  onChange: (points: ExtractionPoint[]) => void
  error?: string
}

// Default extraction points that can't be deleted
const DEFAULT_FIELDS = [
  'Participants',
  'Pain Points',
  'Budget',
  'Timeline',
  'Next Steps',
  'Competitors'
]

// Icon mapping for common field names
const getIconForField = (name: string) => {
  const lowerName = name.toLowerCase()
  if (lowerName.includes('participant')) return User
  if (lowerName.includes('pain')) return Info
  if (lowerName.includes('budget') || lowerName.includes('price')) return DollarSign
  if (lowerName.includes('timeline') || lowerName.includes('deadline')) return Calendar
  if (lowerName.includes('next') || lowerName.includes('action')) return ArrowRight
  if (lowerName.includes('competitor')) return Building2
  return FileText // Default icon
}

const ExtractionPointsConfig: React.FC<ExtractionPointsConfigProps> = ({
  value = [],
  onChange,
  error
}) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editingNameIndex, setEditingNameIndex] = useState<number | null>(null)
  const textareaRefs = useRef<{ [key: number]: HTMLTextAreaElement | null }>({})

  const addExtractionPoint = () => {
    const newPoint: ExtractionPoint = {
      name: '',
      description: '',
      required: false,
      type: 'string'
    }
    const newPoints = [...value, newPoint]
    onChange(newPoints)
    // Auto-focus on editing the new field
    setTimeout(() => {
      setEditingNameIndex(newPoints.length - 1)
    }, 100)
  }

  const removeExtractionPoint = (index: number) => {
    const newPoints = value.filter((_, i) => i !== index)
    onChange(newPoints)
  }

  const toggleRequired = (index: number, e: React.MouseEvent) => {
    e.stopPropagation()
    const newPoints = [...value]
    newPoints[index] = { ...newPoints[index], required: !newPoints[index].required }
    onChange(newPoints)
  }

  const updateField = (index: number, field: keyof ExtractionPoint, newValue: any) => {
    const newPoints = [...value]
    newPoints[index] = { ...newPoints[index], [field]: newValue }
    onChange(newPoints)
  }

  const isCustomField = (name: string) => {
    return !DEFAULT_FIELDS.includes(name)
  }

  const handleDescriptionClick = (index: number) => {
    setEditingIndex(index)
    setTimeout(() => {
      textareaRefs.current[index]?.focus()
    }, 0)
  }

  const handleDescriptionBlur = (index: number) => {
    setEditingIndex(null)
  }

  const handleNameClick = (index: number) => {
    if (isCustomField(value[index].name)) {
      setEditingNameIndex(index)
    }
  }

  const handleNameBlur = () => {
    setEditingNameIndex(null)
  }

  useEffect(() => {
    // Auto-resize textareas
    Object.keys(textareaRefs.current).forEach(key => {
      const textarea = textareaRefs.current[parseInt(key)]
      if (textarea) {
        textarea.style.height = 'auto'
        textarea.style.height = textarea.scrollHeight + 'px'
      }
    })
  }, [value, editingIndex])

  return (
    <div className="space-y-4">
      <p className="text-sm text-scurry-latte leading-relaxed">
        Configure what information to extract from transcripts. These fields will be available as variables in other components - like magic! ✨
      </p>

      {error && (
        <div className="flex items-center space-x-2 p-3 bg-red-50 border border-red-200 rounded-md">
          <AlertCircle className="h-4 w-4 text-red-600" />
          <span className="text-sm text-red-700">{error}</span>
        </div>
      )}

      <div className="space-y-3">
        {value.map((point, index) => {
          const Icon = getIconForField(point.name)
          const isCustom = isCustomField(point.name)
          const isEditingDescription = editingIndex === index
          const isEditingName = editingNameIndex === index

          return (
            <div
              key={index}
              className="group bg-white border border-scurry-foam rounded-lg hover:border-scurry-latte/30 hover:shadow-sm transition-all"
            >
              <div className="flex items-start space-x-3 p-4">
                <div className="w-10 h-10 bg-scurry-orange/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Icon className="h-5 w-5 text-scurry-orange" />
                </div>
                <div className="flex-1 min-w-0 space-y-2">
                  {/* Field Name */}
                  <div className="flex items-center space-x-2">
                    {isEditingName ? (
                      <Input
                        value={point.name}
                        onChange={(e) => updateField(index, 'name', e.target.value)}
                        onBlur={handleNameBlur}
                        placeholder="Field name"
                        className="font-medium text-gray-900"
                        autoFocus
                      />
                    ) : (
                      <h4
                        className={`font-medium text-scurry-espresso ${isCustom ? 'cursor-pointer hover:text-scurry-orange' : ''}`}
                        onClick={() => handleNameClick(index)}
                      >
                        {point.name || <span className="text-gray-400 italic">Click to add name</span>}
                      </h4>
                    )}
                    <Badge
                      variant={point.required ? "default" : "secondary"}
                      className={`cursor-pointer text-xs font-semibold ${point.required
                        ? "bg-scurry-orange text-white hover:bg-scurry-orange-hover"
                        : "bg-scurry-latte/25 text-scurry-latte hover:bg-scurry-latte/35"
                      }`}
                      onClick={(e) => toggleRequired(index, e)}
                    >
                      {point.required ? "🥜 Must Gather" : "Bonus Nut"}
                    </Badge>
                  </div>

                  {/* Description - Inline Editable */}
                  {isEditingDescription ? (
                    <Textarea
                      ref={(el) => { textareaRefs.current[index] = el }}
                      value={point.description}
                      onChange={(e) => updateField(index, 'description', e.target.value)}
                      onBlur={() => handleDescriptionBlur(index)}
                      placeholder="Click to add description / AI instructions..."
                      className="text-sm resize-none"
                      rows={3}
                    />
                  ) : (
                    <p
                      className="text-sm text-scurry-latte cursor-pointer hover:bg-scurry-foam/50 p-2 rounded transition-colors"
                      onClick={() => handleDescriptionClick(index)}
                    >
                      {point.description || <span className="text-scurry-latte/60 italic">Click to add description / AI instructions...</span>}
                    </p>
                  )}
                </div>
                {isCustom && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      removeExtractionPoint(index)
                    }}
                    className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <Button
        type="button"
        onClick={addExtractionPoint}
        variant="outline"
        className="w-full border-dashed border-scurry-latte/30 text-scurry-latte hover:text-scurry-orange hover:border-scurry-orange/50 hover:bg-scurry-orange/5"
      >
        <Plus className="h-4 w-4 mr-2" />
        Add Custom Field
      </Button>
    </div>
  )
}

export default ExtractionPointsConfig
