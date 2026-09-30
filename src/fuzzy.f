/*
    Deterministic, case-insensitive Levenshtein matching over UTF-8 bytes.
    Public API: the exported `fuzzy` facade. All helpers are private.
*/

struct(fuzzy) {
    private fn(fail()) {
        invalid_value := null
        return invalid_value.length()
    }

    private fn(string(value)) {
        if(type(value) != "string") { return this.fail() }
        return value
    }

    private fn(limit(options)) {
        if(options.size() > 1) { return this.fail() }
        maximum := 2
        if(options.size() == 1) { maximum = options[0] }
        if(type(maximum) != "int" || maximum < 0) { return this.fail() }
        return maximum
    }

    private fn(candidate_list(candidates)) {
        if(type(candidates) != "array") { return this.fail() }
        for(candidate : candidates) { this.string(candidate) }
        return candidates
    }

    private fn(fold(value)) {
        source := value.encode("utf-8")
        folded := []
        i := 0
        while(i < source.length()) {
            byte := source[i].to_int()
            if(byte >= 65 && byte <= 90) { byte += 32 }
            folded.push(byte)
            i += 1
        }
        return folded
    }

    private fn(distance_folded(first, second)) {
        previous := []
        j := 0
        while(j <= second.length()) { previous.push(j); j += 1 }

        i := 1
        while(i <= first.length()) {
            current := [i]
            j = 1
            while(j <= second.length()) {
                deletion := previous[j] + 1
                insertion := current[j - 1] + 1
                substitution := previous[j - 1]
                if(first[i - 1] != second[j - 1]) { substitution += 1 }
                best := deletion
                if(insertion < best) { best = insertion }
                if(substitution < best) { best = substitution }
                current.push(best)
                j += 1
            }
            previous = current
            i += 1
        }
        return previous[second.length()] + 0
    }

    private fn(insert_ranked(ranked, item)) {
        result := []
        inserted := false
        for(existing : ranked) {
            if(!inserted && item.distance < existing.distance) {
                result.push(item)
                inserted = true
            }
            result.push(existing)
        }
        if(!inserted) { result.push(item) }
        return result
    }

    fn(distance(a, b)) {
        this.string(a)
        this.string(b)
        first := this.fold(a)
        second := this.fold(b)
        return this.distance_folded(first, second)
    }

    fn(matches(query, candidate, ...options)) {
        maximum := this.limit(options)
        return this.distance(query, candidate) <= maximum
    }

    fn(filter(query, candidates, ...options)) {
        this.string(query)
        this.candidate_list(candidates)
        maximum := this.limit(options)
        result := []
        for(candidate : candidates) {
            if(this.distance(query, candidate) <= maximum) { result.push(candidate) }
        }
        return result
    }

    fn(rank(query, candidates)) {
        this.string(query)
        this.candidate_list(candidates)
        ranked := []
        for(candidate : candidates) {
            item := {"candidate":candidate,"distance":this.distance(query, candidate)}
            ranked = this.insert_ranked(ranked, item)
        }
        return ranked
    }
}

fuzzy := fuzzy()
export(fuzzy)
